import json
import logging
import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection
from django.db.models.functions import Length
from django.http import (
    Http404,
    HttpRequest,
    HttpResponseRedirect,
    JsonResponse,
)
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
from django_ratelimit.decorators import ratelimit

from ark.forms import MintArkForm, UpdateArkForm
from ark.models import Ark, ArkEvent, Key, Naan, Shoulder
from ark.utils import parse_ark, gen_prefixes, parse_ark_lookup

COLLISIONS = 10

logger = logging.getLogger(__name__)

EVENT_FIELDS = [
    "url",
    "title",
    "type",
    "commitment",
    "identifier",
    "format",
    "relation",
    "source",
    "metadata",
    "cdn_url",
    "event_name",
    "related_arks",
    "state",
    "replaced_by",
    "tombstone_reason",
]


def request_id_for(request: HttpRequest) -> str:
    return getattr(request, "request_id", "")


def error_response(
    request: HttpRequest,
    *,
    status: int,
    code: str,
    message: str,
    details=None,
):
    return JsonResponse(
        {
            "code": code,
            "message": message,
            "details": details if details is not None else {},
            "request_id": request_id_for(request),
        },
        status=status,
    )


def event_snapshot(ark: Ark):
    return {field: getattr(ark, field) for field in EVENT_FIELDS}


def event_diff(before: dict, after: dict):
    return {
        field: {"from": before.get(field), "to": after.get(field)}
        for field in EVENT_FIELDS
        if before.get(field) != after.get(field)
    }


def create_ark_event(request: HttpRequest, ark_obj: Ark, event_type: str, diff: dict):
    actor_key = getattr(request, "authorized_key", None)
    ArkEvent.objects.create(
        ark=ark_obj,
        event_type=event_type,
        actor_key_hash=getattr(actor_key, "key", ""),
        ip=request.META.get("REMOTE_ADDR", ""),
        diff_json=diff,
    )


def resolve_related_arks(ark_obj: Ark):
    """Return related ARKs with bidirectional inverse relations resolved."""
    seen = set()
    results = []

    # Forward relations stored on this ark
    for item in ark_obj.related_arks or []:
        target_ark = item.get("ark", "")
        if target_ark in seen:
            continue
        seen.add(target_ark)
        results.append(
            {
                "ark": target_ark,
                "relation": item.get("relation", ""),
                "label": item.get("label", ""),
                "direction": "forward",
            }
        )

    # Inverse relations: find arks that point to this one
    try:
        inverse_qs = Ark.objects.filter(
            related_arks__contains=[{"ark": f"ark:/{ark_obj.ark}"}]
        )
    except Exception:
        inverse_qs = []

    for other in inverse_qs:
        if other.ark == ark_obj.ark:
            continue
        other_ark_str = f"ark:/{other.ark}"
        if other_ark_str in seen:
            continue
        seen.add(other_ark_str)
        # Determine inverse relation label
        for item in other.related_arks or []:
            if item.get("ark") == f"ark:/{ark_obj.ark}":
                rel = item.get("relation", "")
                inv_rel = Ark.INVERSE_RELATIONS.get(rel, "related")
                label = item.get("label", "")
                inv_label = Ark.INVERSE_RELATIONS.get(label, label) if label else ""
                results.append(
                    {
                        "ark": other_ark_str,
                        "relation": inv_rel,
                        "label": inv_label or inv_rel,
                        "direction": "inverse",
                    }
                )
                break

    return results


def authorize(request, naan):
    bearer_token = request.headers.get("Authorization")
    if not bearer_token:
        return None

    key = bearer_token.split()[-1]

    try:
        keys = Key.objects.filter(naan=naan, active=True)
        for k in keys:
            if k.check_password(key):
                return k
        return None
    except ValidationError as e:  # probably an invalid key
        return None


@ratelimit(key="ip", rate="60/m", block=True)
@csrf_exempt
def mint_ark(request):
    if request.method != "POST":
        return error_response(
            request,
            status=405,
            code="method_not_allowed",
            message="Only POST is allowed for this endpoint",
            details={"allowed_methods": ["POST"]},
        )

    try:
        unsafe_mint_request = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, TypeError):
        return error_response(
            request,
            status=400,
            code="invalid_json",
            message="Request body must be valid JSON",
        )

    mint_request = MintArkForm(unsafe_mint_request)

    if not mint_request.is_valid():
        return error_response(
            request,
            status=400,
            code="validation_error",
            message="Mint payload validation failed",
            details=mint_request.errors,
        )

    # Pop these keys so that we can pass the cleaned data
    # dict directly to the create method later
    naan = mint_request.cleaned_data.pop("naan")
    authorized_key = authorize(request, naan)
    if authorized_key is None:
        return error_response(
            request,
            status=403,
            code="forbidden",
            message="Invalid or missing authorization key",
        )
    request.authorized_key = authorized_key
    authorized_naan = authorized_key.naan

    shoulder = mint_request.cleaned_data.pop("shoulder")
    shoulder_obj = Shoulder.objects.filter(shoulder=shoulder).first()
    if shoulder_obj is None:
        return error_response(
            request,
            status=400,
            code="invalid_shoulder",
            message=f"Shoulder {shoulder} does not exist",
        )

    ark, collisions = None, 0
    for _ in range(10):
        try:
            ark = Ark.create(authorized_naan, shoulder_obj)
            ark.set_fields(mint_request.cleaned_data)
            ark.save()
            break
        except IntegrityError:
            collisions += 1
            continue

    if not ark:
        msg = f"Gave up creating ark after {collisions} collision(s)"
        logger.error(msg)
        return error_response(
            request,
            status=500,
            code="mint_collision_limit",
            message=msg,
        )
    if ark and collisions > 0:
        logger.warning("Ark created after %d collision(s)", collisions)

    create_ark_event(
        request,
        ark,
        ArkEvent.EVENT_MINT,
        {"created": event_snapshot(ark)},
    )

    logger.info(
        "mint naan=%s ark=%s ip=%s",
        authorized_naan,
        ark,
        request.META.get("REMOTE_ADDR"),
    )
    return JsonResponse({"ark": str(ark)})


@ratelimit(key="ip", rate="60/m", block=True)
@csrf_exempt
def update_ark(request):
    if request.method != "PUT":
        return error_response(
            request,
            status=405,
            code="method_not_allowed",
            message="Only PUT is allowed for this endpoint",
            details={"allowed_methods": ["PUT"]},
        )

    try:
        unsafe_update_request = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, TypeError):
        return error_response(
            request,
            status=400,
            code="invalid_json",
            message="Request body must be valid JSON",
        )

    # TODO: test input data with wrong structure
    update_request = UpdateArkForm(unsafe_update_request)

    if not update_request.is_valid():
        return error_response(
            request,
            status=400,
            code="validation_error",
            message="Update payload validation failed",
            details=update_request.errors,
        )

    # The ark field is immutable, pop it out of the cleaned
    # data dictionary here so we don't try to update it later
    ark = update_request.cleaned_data.pop("ark")

    _, naan, assigned_name = parse_ark(ark)

    authorized_key = authorize(request, naan)
    if authorized_key is None:
        return error_response(
            request,
            status=403,
            code="forbidden",
            message="Invalid or missing authorization key",
        )
    request.authorized_key = authorized_key
    authorized_naan = authorized_key.naan

    try:
        ark_obj = Ark.objects.get(ark=f"{naan}/{assigned_name}")
    except Ark.DoesNotExist:
        return error_response(
            request,
            status=404,
            code="ark_not_found",
            message=f"ARK {ark} was not found",
        )

    before = event_snapshot(ark_obj)
    ark_obj.set_fields(update_request.cleaned_data)
    ark_obj.save()
    diff = event_diff(before, event_snapshot(ark_obj))
    create_ark_event(request, ark_obj, ArkEvent.EVENT_UPDATE, diff)

    logger.info(
        "update naan=%s ark=%s ip=%s",
        authorized_naan,
        ark,
        request.META.get("REMOTE_ADDR"),
    )
    return JsonResponse(ark_to_json(ark_obj, metadata=False))


def resolve_ark(request, ark: str):
    info_inflection = "info" in request.GET
    json_inflection = "json" in request.GET

    try:
        _, naan, identifier = parse_ark(ark)
    except ValueError as e:
        return error_response(
            request,
            status=400,
            code="invalid_ark",
            message=str(e),
        )

    ark_str = f"{naan}/{identifier}"
    ark_obj = Ark.objects.filter(ark=ark_str).first()
    if ark_obj:
        is_tombstoned = ark_obj.state == Ark.STATE_TOMBSTONED

        if info_inflection:
            return view_ark(
                request,
                ark_obj,
                status_code=410 if is_tombstoned else 200,
            )
        if json_inflection:
            return json_ark(
                request,
                ark_obj,
                status_code=410 if is_tombstoned else 200,
            )
        if is_tombstoned:
            return view_ark(request, ark_obj, status_code=410)
        if not ark_obj.url:
            return view_ark(request, ark_obj)

        query_params = request.GET.copy()
        query_params.pop("info", None)
        query_params.pop("json", None)
        querystring = query_params.urlencode()
        redirect_url = ark_obj.url
        if querystring:
            separator = "&" if "?" in redirect_url else "?"
            redirect_url = f"{redirect_url}{separator}{querystring}"
        return HttpResponseRedirect(redirect_url)
    else:
        # Ark not found. Try to find an ark that is a prefix.
        prefixes = [f"{naan}/{a}" for a in gen_prefixes(identifier)]
        # Get the one with the longest prefix
        ark_prefix = (
            Ark.objects.filter(ark__in=prefixes).order_by(Length("ark")).first()
        )
        if ark_prefix:
            suffix = ark_str.removeprefix(ark_prefix.ark)
            return HttpResponseRedirect(ark_prefix.url + suffix)
        else:
            if info_inflection or json_inflection:
                raise Http404
            try:
                naan_obj = Naan.objects.get(naan=naan)
                return HttpResponseRedirect(f"{naan_obj.url}/ark:/{ark_str}")
            except Naan.DoesNotExist:
                resolver = settings.ARK_FALLBACK_RESOLVER
                return HttpResponseRedirect(f"{resolver}/ark:/{ark_str}")


"""
Return HTML human readable webpage information about the Ark object
"""


def view_ark(request: HttpRequest, ark: Ark, status_code=200):
    related = resolve_related_arks(ark)

    context = {
        "ark": ark.ark,
        "url": ark.url,
        "label": ark.title,
        "type": ark.type,
        "commitment": ark.commitment,
        "identifier": ark.identifier,
        "format": ark.format,
        "relation": ark.relation,
        "source": ark.source,
        "metadata": ark.metadata,
        "cdn_url": ark.cdn_url,
        "event_name": ark.event_name,
        "related_arks": related,
        "state": ark.state,
        "replaced_by": ark.replaced_by,
        "tombstone_reason": ark.tombstone_reason,
    }

    return render(request, "info.html", context, status=status_code)


"""
Return the Ark object as JSON
"""


def ark_to_json(ark: Ark, metadata=True):
    data = {
        "ark": ark.ark,
        "url": ark.url,
        "title": ark.title,
        "type": ark.type,
        "commitment": ark.commitment,
        "identifier": ark.identifier,
        "format": ark.format,
        "relation": ark.relation,
        "source": ark.source,
        "metadata": ark.metadata,
        "cdn_url": ark.cdn_url,
        "event_name": ark.event_name,
        "related_arks": resolve_related_arks(ark),
        "state": ark.state,
        "replaced_by": ark.replaced_by,
        "tombstone_reason": ark.tombstone_reason,
    }
    if not metadata:
        return data
    obj = {}
    for key in data:
        obj[key] = Ark.COLUMN_METADATA.get(key, {})
        obj[key]["value"] = data[key]
    return obj


def json_ark(request: HttpRequest, ark: Ark, status_code=200):
    obj = ark_to_json(ark)
    # Return the JSON response
    return JsonResponse(obj, status=status_code)


@ratelimit(key="ip", rate="60/m", block=True)
@csrf_exempt
def batch_query_arks(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, TypeError):
        return error_response(
            request,
            status=400,
            code="invalid_json",
            message="Request body must be valid JSON",
        )

    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        return error_response(
            request,
            status=400,
            code="invalid_payload",
            message="Expected a JSON list or an object with a 'data' list",
        )
    if len(data) > 100:
        return error_response(
            request,
            status=400,
            code="batch_limit_exceeded",
            message="Exceeded max rows (100)",
            details={"max_rows": 100},
        )
    try:
        arks = [parse_ark_lookup(d.get("ark")) for d in data]
    except (AttributeError, TypeError, ValueError):
        return error_response(
            request,
            status=400,
            code="invalid_ark",
            message="Each record must contain a valid 'ark' value",
        )
    ark_objs = Ark.objects.filter(ark__in=arks)
    resp = [ark_to_json(ark, metadata=False) for ark in ark_objs]
    return JsonResponse(resp, safe=False)


@ratelimit(key="ip", rate="60/m", block=True)
@csrf_exempt
def batch_update_arks(request):
    try:
        data = json.loads(request.body.decode("utf-8"))["data"]
    except (json.JSONDecodeError, TypeError):
        return error_response(
            request,
            status=400,
            code="invalid_json",
            message="Request body must be valid JSON",
        )
    except KeyError:
        return error_response(
            request,
            status=400,
            code="invalid_payload",
            message="Expected a 'data' field containing a list",
        )
    if len(data) > 100:
        return error_response(
            request,
            status=400,
            code="batch_limit_exceeded",
            message="Exceeded max rows (100)",
            details={"max_rows": 100},
        )

    naans = set()
    for d in data:
        if "ark" not in d:
            return error_response(
                request,
                status=400,
                code="invalid_payload",
                message="Each record must have an 'ark' field.",
            )
        try:
            _, naan, _ = parse_ark(d["ark"])
        except (AttributeError, TypeError, ValueError):
            return error_response(
                request,
                status=400,
                code="invalid_ark",
                message="Each record must contain a valid 'ark' value",
            )
        naans.add(naan)

    if len(naans) != 1:
        return error_response(
            request,
            status=400,
            code="invalid_payload",
            message="Batch queries are limited to one NAAN at a time",
        )

    naan = naans.pop()
    authorized_key = authorize(request, naan)
    if authorized_key is None:
        return error_response(
            request,
            status=403,
            code="forbidden",
            message="Invalid or missing authorization key",
        )
    request.authorized_key = authorized_key

    try:
        arks = [parse_ark_lookup(d.get("ark")) for d in data]
    except (AttributeError, TypeError, ValueError):
        return error_response(
            request,
            status=400,
            code="invalid_ark",
            message="Each record must contain a valid 'ark' value",
        )
    ark_objs = Ark.objects.filter(ark__in=arks)
    ark_lookup = {ark_obj.ark: ark_obj for ark_obj in ark_objs}

    # track the fields we have seen so far for efficient updating
    seen_fields = set()
    to_update = []
    missing = []
    event_rows = []
    for new_record in data:
        ark = parse_ark_lookup(new_record["ark"])
        ark_obj = ark_lookup.get(ark)
        if ark_obj is None:
            missing.append(new_record["ark"])
            continue
        before = event_snapshot(ark_obj)
        ark_obj.set_fields(new_record)
        diff = event_diff(before, event_snapshot(ark_obj))
        seen_fields.update(new_record.keys())
        to_update.append(ark_obj)
        event_rows.append((ark_obj, diff))
    # don't update primary key
    seen_fields.discard("ark")
    n_updated = 0
    if to_update and seen_fields:
        n_updated = Ark.objects.bulk_update(to_update, fields=seen_fields)
        actor_key_hash = getattr(request.authorized_key, "key", "")
        ip = request.META.get("REMOTE_ADDR", "")
        ArkEvent.objects.bulk_create(
            [
                ArkEvent(
                    ark=ark_obj,
                    event_type=ArkEvent.EVENT_BATCH_UPDATE,
                    actor_key_hash=actor_key_hash,
                    ip=ip,
                    diff_json=diff,
                )
                for ark_obj, diff in event_rows
            ]
        )
    logger.info(
        "batch_update naan=%s count=%d ip=%s",
        naan,
        n_updated,
        request.META.get("REMOTE_ADDR"),
    )
    return JsonResponse(
        {
            "num_received": len(data),
            "num_updated": n_updated,
            "num_missing": len(missing),
            "missing_arks": missing,
        }
    )


@ratelimit(key="ip", rate="60/m", block=True)
@csrf_exempt
def batch_mint_arks(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, TypeError):
        return error_response(
            request,
            status=400,
            code="invalid_json",
            message="Request body must be valid JSON",
        )

    naan = data.get("naan")
    authorized_key = authorize(request, naan)
    if authorized_key is None:
        return error_response(
            request,
            status=403,
            code="forbidden",
            message="Invalid or missing authorization key",
        )
    request.authorized_key = authorized_key
    authorized_naan = authorized_key.naan
    records = data.get("data")
    if not isinstance(records, list):
        return error_response(
            request,
            status=400,
            code="invalid_payload",
            message="Expected a 'data' field containing a list",
        )

    if len(records) > 100:
        return error_response(
            request,
            status=400,
            code="batch_limit_exceeded",
            message="Exceeded max rows (100)",
            details={"max_rows": 100},
        )

    shoulders = set()
    for d in records:
        if "shoulder" not in d:
            return error_response(
                request,
                status=400,
                code="invalid_payload",
                message="shoulder value must be present in every record",
            )
        shoulders.add(d["shoulder"])
    shoulder_objs = dict()
    for s in shoulders:
        shoulder_obj = Shoulder.objects.filter(shoulder=s).first()
        if shoulder_obj is None:
            return error_response(
                request,
                status=400,
                code="invalid_shoulder",
                message=f"shoulder {s} does not exist",
            )
        shoulder_objs[s] = shoulder_obj

    created = None
    for _ in range(COLLISIONS):
        # Attempt to mint the batch with max COLLISION retries times
        try:
            new_arks = []
            for record in records:
                shoulder = shoulder_objs[record["shoulder"]]
                new_ark = Ark.create(authorized_naan, shoulder)
                new_ark.set_fields(record)
                new_arks.append(new_ark)
            created = Ark.objects.bulk_create(new_arks)
        except IntegrityError:
            continue
        break
    else:
        msg = f"Gave up creating bulk arks after {COLLISIONS} collision(s)"
        logger.error(msg)
        return error_response(
            request,
            status=500,
            code="mint_collision_limit",
            message=msg,
        )
    logger.info(
        "batch_mint naan=%s count=%d ip=%s",
        naan,
        len(created),
        request.META.get("REMOTE_ADDR"),
    )
    actor_key_hash = getattr(request.authorized_key, "key", "")
    ip = request.META.get("REMOTE_ADDR", "")
    ArkEvent.objects.bulk_create(
        [
            ArkEvent(
                ark=ark_obj,
                event_type=ArkEvent.EVENT_BATCH_MINT,
                actor_key_hash=actor_key_hash,
                ip=ip,
                diff_json={"created": event_snapshot(ark_obj)},
            )
            for ark_obj in created
        ]
    )
    return JsonResponse(
        {
            "num_received": len(records),
            "arks_created": [ark_to_json(c, metadata=False) for c in created],
        }
    )


@ratelimit(key="ip", rate="60/m", block=True)
def history_ark(request):
    if request.method != "GET":
        return error_response(
            request,
            status=405,
            code="method_not_allowed",
            message="Only GET is allowed for this endpoint",
            details={"allowed_methods": ["GET"]},
        )

    ark = request.GET.get("ark")
    if not ark:
        return error_response(
            request,
            status=400,
            code="invalid_payload",
            message="Query parameter 'ark' is required",
        )

    try:
        ark_lookup = parse_ark_lookup(ark)
    except ValueError as e:
        return error_response(
            request,
            status=400,
            code="invalid_ark",
            message=str(e),
        )

    try:
        limit = int(request.GET.get("limit", 20))
    except ValueError:
        return error_response(
            request,
            status=400,
            code="invalid_payload",
            message="Query parameter 'limit' must be an integer",
        )

    if limit < 1 or limit > 100:
        return error_response(
            request,
            status=400,
            code="invalid_payload",
            message="Query parameter 'limit' must be between 1 and 100",
        )

    events = ArkEvent.objects.filter(ark_id=ark_lookup).order_by("-created_at")[:limit]
    payload = [
        {
            "event_type": event.event_type,
            "created_at": event.created_at.isoformat(),
            "actor_key_hash": event.actor_key_hash,
            "ip": event.ip,
            "diff": event.diff_json,
        }
        for event in events
    ]
    return JsonResponse(
        {"ark": f"ark:/{ark_lookup}", "count": len(payload), "events": payload}
    )


def status(request):
    service = "resolver" if os.environ.get("RESOLVER") else "minter"

    return JsonResponse(
        {
            "service": service,
            "status": "ok!",
        }
    )


def api_docs(request):
    return render(request, "swagger_ui.html")


def health_check(request):
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False
    status_code = 200 if db_ok else 503
    return JsonResponse(
        {"status": "ok" if db_ok else "degraded", "db": db_ok}, status=status_code
    )
