import csv
import os

import click
import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

console = Console()

DEFAULT_URL = os.environ.get("ARK_API_URL", "http://127.0.0.1:8001")

METADATA_FIELDS = [
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
]


class ArkAPIError(click.ClickException):
    def show(self):
        console.print(f"[bold red]Error:[/bold red] {self.format_message()}")


def _request(method, path, ok_statuses=None, **kwargs):
    url = f"{DEFAULT_URL}/{path}"
    try:
        response = requests.request(method.upper(), url, timeout=10, **kwargs)
    except requests.exceptions.ConnectionError:
        raise ArkAPIError(f"Cannot connect to {DEFAULT_URL}")
    except requests.exceptions.Timeout:
        raise ArkAPIError("Request timed out")

    if ok_statuses is None:
        status_ok = 200 <= response.status_code < 300
    else:
        status_ok = response.status_code in ok_statuses

    if status_ok:
        if not response.text.strip():
            return {}
        return response.json()

    request_id = response.headers.get("X-Request-ID")
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        code = payload.get("code", "unknown_error")
        message = payload.get("message", response.text.strip())
        details = payload.get("details")
        payload_request_id = payload.get("request_id") or request_id
        msg = f"HTTP {response.status_code} [{code}] {message}"
        if details:
            msg += f" | details: {details}"
        if payload_request_id:
            msg += f" | request_id: {payload_request_id}"
        raise ArkAPIError(msg)

    msg = f"HTTP {response.status_code}: {response.text.strip()}"
    if request_id:
        msg += f" | request_id: {request_id}"
    raise ArkAPIError(msg)


def _authed(method, path, data, **kwargs):
    key = os.environ.get("ARK_API_KEY", "")
    if not key:
        raise ArkAPIError("ARK_API_KEY environment variable is not set")
    return _request(method, path, json=data, headers={"Authorization": key}, **kwargs)


def _csv2json(path):
    with open(path, "rt") as f:
        return list(csv.DictReader(f))


def _metadata_table(data: dict, title: str = "") -> Table:
    table = Table(
        box=box.ROUNDED, show_header=True, header_style="bold cyan", title=title
    )
    table.add_column("Field", style="dim")
    table.add_column("Value")
    for key, val in data.items():
        value = val.get("value", val) if isinstance(val, dict) else val
        if value:
            table.add_row(str(key), str(value))
    return table


def _metadata_kwargs(
    url,
    title,
    type_,
    commitment,
    identifier,
    format_,
    relation,
    source,
    metadata,
    cdn_url,
    event_name,
    related_arks,
):
    return {
        k: v
        for k, v in {
            "url": url,
            "title": title,
            "type": type_,
            "commitment": commitment,
            "identifier": identifier,
            "format": format_,
            "relation": relation,
            "source": source,
            "metadata": metadata,
            "cdn_url": cdn_url,
            "event_name": event_name,
            "related_arks": related_arks,
        }.items()
        if v is not None
    }


def _tombstone_kwargs(state, replaced_by, tombstone_reason):
    return {
        k: v
        for k, v in {
            "state": state,
            "replaced_by": replaced_by,
            "tombstone_reason": tombstone_reason,
        }.items()
        if v is not None
    }


def _metadata_options(f):
    for opt, help_ in [
        ("--url", "Target URL"),
        ("--title", "dc:title"),
        ("--type", "dc:type"),
        ("--commitment", "Commitment statement"),
        ("--identifier", "dc:identifier"),
        ("--format", "dc:format"),
        ("--relation", "dc:relation (URL)"),
        ("--source", "dc:source (URL)"),
        ("--metadata", "Free-form metadata"),
        ("--cdn-url", "CDN URL (image/PDF)"),
        ("--event-name", "Event or venue name"),
        (
            "--related-arks",
            "JSON list of related ARKs, e.g. "
            '[{"ark":"ark:/...","relation":"hasBack","label":"Rückseite"}]\'',
        ),
    ]:
        f = click.option(opt, default=None, help=help_)(f)
    return f


@click.group()
def cli():
    """ARK identifier API — mint, update, query, and resolve ARKs."""


@cli.command()
def status():
    """Show service status."""
    data = _request("get", "")
    panel = Panel(
        f"[bold green]{data.get('status', '?')}[/bold green]\n"
        f"Service: [cyan]{data.get('service', '?')}[/cyan]\n"
        f"Host:    [dim]{DEFAULT_URL}[/dim]",
        title="ARK Service",
        border_style="green",
    )
    console.print(panel)


@cli.command()
@click.option("--ark", required=True, help="ARK identifier (e.g. ark:/12345/abc)")
def query(ark):
    """Query metadata for a single ARK."""
    data = _request("get", f"{ark}?json", ok_statuses={200, 410})
    state = data.get("state", {}).get("value")
    if state == "tombstoned":
        console.print("[yellow]Note:[/yellow] ARK is tombstoned (HTTP 410).")
    console.print(_metadata_table(data, title=f"[bold]{ark}[/bold]"))


@cli.command()
@click.option("--naan", required=True, type=int, help="Name Assigning Authority Number")
@click.option("--shoulder", required=True, help="Shoulder (e.g. /t)")
@_metadata_options
def mint(
    naan,
    shoulder,
    url,
    title,
    type,
    commitment,
    identifier,
    format,
    relation,
    source,
    metadata,
    cdn_url,
    event_name,
    related_arks,
):
    """Mint a new ARK identifier."""
    payload = {
        "naan": naan,
        "shoulder": shoulder,
        **_metadata_kwargs(
            url,
            title,
            type,
            commitment,
            identifier,
            format,
            relation,
            source,
            metadata,
            cdn_url,
            event_name,
            related_arks,
        ),
    }
    data = _authed("post", "mint", payload)
    ark = data.get("ark", "?")
    console.print(
        Panel(
            f"[bold green]{ark}[/bold green]", title="Minted ARK", border_style="green"
        )
    )


@cli.command()
@click.option("--ark", required=True, help="ARK identifier to update")
@_metadata_options
@click.option(
    "--state",
    type=click.Choice(["active", "tombstoned"]),
    default=None,
    help="Resource state",
)
@click.option("--replaced-by", default=None, help="Replacement ARK")
@click.option("--tombstone-reason", default=None, help="Tombstone reason")
def update(
    ark,
    url,
    title,
    type,
    commitment,
    identifier,
    format,
    relation,
    source,
    metadata,
    cdn_url,
    event_name,
    related_arks,
    state,
    replaced_by,
    tombstone_reason,
):
    """Update an existing ARK identifier."""
    payload = {
        "ark": ark,
        **_metadata_kwargs(
            url,
            title,
            type,
            commitment,
            identifier,
            format,
            relation,
            source,
            metadata,
            cdn_url,
            event_name,
            related_arks,
        ),
        **_tombstone_kwargs(state, replaced_by, tombstone_reason),
    }
    data = _authed("put", "update", payload)
    console.print(_metadata_table(data, title=f"[bold]Updated: {ark}[/bold]"))


@cli.command()
@click.option("--ark", required=True, help="ARK identifier to tombstone")
@click.option("--replaced-by", default=None, help="Replacement ARK")
@click.option(
    "--reason",
    default=None,
    help="Human-readable reason for tombstoning",
)
def tombstone(ark, replaced_by, reason):
    """Mark an ARK as tombstoned."""
    payload = {
        "ark": ark,
        **_tombstone_kwargs("tombstoned", replaced_by, reason),
    }
    data = _authed("put", "update", payload)
    console.print(_metadata_table(data, title=f"[bold]Tombstoned: {ark}[/bold]"))


@cli.command()
@click.option("--ark", required=True, help="ARK identifier to inspect")
@click.option("--limit", default=20, show_default=True, type=int, help="Max events")
def history(ark, limit):
    """Show recent change history for one ARK."""
    data = _request("get", "history", params={"ark": ark, "limit": limit})
    events = data.get("events", [])
    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold cyan",
        title=f"History: {data.get('ark', ark)}",
    )
    table.add_column("When")
    table.add_column("Type")
    table.add_column("IP")
    table.add_column("Changes")
    for event in events:
        diff = event.get("diff", {})
        changed = ", ".join(diff.keys()) if diff else "-"
        table.add_row(
            str(event.get("created_at", "")),
            str(event.get("event_type", "")),
            str(event.get("ip") or ""),
            changed,
        )
    console.print(table)
    console.print(f"[dim]{data.get('count', 0)} event(s)[/dim]")


@cli.group()
def bulk():
    """Bulk operations on multiple ARKs via CSV."""


@bulk.command("query")
@click.argument("csv_file", type=click.Path(exists=True))
def bulk_query(csv_file):
    """Query multiple ARKs from CSV (requires 'ark' column)."""
    rows = _csv2json(csv_file)
    if "ark" not in rows[0]:
        raise ArkAPIError("CSV must include an 'ark' column")
    with console.status(f"Querying {len(rows)} ARKs…"):
        results = _request("post", "bulk_query", json=rows)
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold cyan")
    if results:
        for col in results[0]:
            table.add_column(col)
        for row in results:
            table.add_row(*[str(v or "") for v in row.values()])
    console.print(table)
    console.print(f"[dim]{len(results)} result(s)[/dim]")


@bulk.command("mint")
@click.option("--naan", required=True, type=int, help="NAAN for all minted ARKs")
@click.argument("csv_file", type=click.Path(exists=True))
def bulk_mint(naan, csv_file):
    """Mint ARKs from CSV (requires 'shoulder' column)."""
    rows = _csv2json(csv_file)
    with console.status(f"Minting {len(rows)} ARKs…"):
        data = _authed("post", "bulk_mint", {"naan": naan, "data": rows})
    created = data.get("arks_created", [])
    table = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        header_style="bold cyan",
        title="Minted ARKs",
    )
    table.add_column("ARK")
    table.add_column("URL")
    for ark in created:
        table.add_row(ark.get("ark", ""), ark.get("url", ""))
    console.print(table)
    console.print(
        f"[green]✓[/green] {len(created)} of {data.get('num_received', '?')} minted"
    )


@bulk.command("update")
@click.argument("csv_file", type=click.Path(exists=True))
def bulk_update(csv_file):
    """Update ARKs from CSV (requires 'ark' column)."""
    rows = _csv2json(csv_file)
    with console.status(f"Updating {len(rows)} ARKs…"):
        data = _authed("post", "bulk_update", {"data": rows})
    console.print(
        f"[green]✓[/green] {data.get('num_updated')} of {data.get('num_received')} updated"
    )


if __name__ == "__main__":
    cli()
