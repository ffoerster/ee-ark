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
]


class ArkAPIError(click.ClickException):
    def show(self):
        console.print(f"[bold red]Error:[/bold red] {self.format_message()}")


def _request(method, path, **kwargs):
    url = f"{DEFAULT_URL}/{path}"
    try:
        response = getattr(requests, method)(url, timeout=10, **kwargs)
    except requests.exceptions.ConnectionError:
        raise ArkAPIError(f"Cannot connect to {DEFAULT_URL}")
    except requests.exceptions.Timeout:
        raise ArkAPIError("Request timed out")
    if response.status_code == 200:
        return response.json()
    raise ArkAPIError(f"HTTP {response.status_code}: {response.text.strip()}")


def _authed(method, path, data):
    key = os.environ.get("ARK_API_KEY", "")
    if not key:
        raise ArkAPIError("ARK_API_KEY environment variable is not set")
    return _request(method, path, json=data, headers={"Authorization": key})


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
    url, title, type_, commitment, identifier, format_, relation, source, metadata
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
    data = _request("get", f"{ark}?json")
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
):
    """Mint a new ARK identifier."""
    payload = {
        "naan": naan,
        "shoulder": shoulder,
        **_metadata_kwargs(
            url, title, type, commitment, identifier, format, relation, source, metadata
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
def update(
    ark, url, title, type, commitment, identifier, format, relation, source, metadata
):
    """Update an existing ARK identifier."""
    payload = {
        "ark": ark,
        **_metadata_kwargs(
            url, title, type, commitment, identifier, format, relation, source, metadata
        ),
    }
    data = _authed("put", "update", payload)
    console.print(_metadata_table(data, title=f"[bold]Updated: {ark}[/bold]"))


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
