"""Render a portable, read-only HTML report from captured execution events."""

from html import escape


_STYLE = """
:root {
  color-scheme: light;
  font: 1rem/1.55 system-ui, sans-serif;
  color: #182b29;
  background: #f4f7f6;
}
body { margin: 0; }
main { max-width: 72rem; padding: 2rem clamp(1rem, 4vw, 3rem) 4rem; margin: auto; }
h1, h2 { line-height: 1.15; margin: 0 0 .8rem; }
h1 { font-size: clamp(2rem, 5vw, 3.25rem); letter-spacing: -.045em; }
h2 { font-size: 1.4rem; }
p { margin: .6rem 0; }
a { color: #125d54; }
a:focus-visible, summary:focus-visible, [tabindex]:focus-visible {
  outline: 3px solid #12695d; outline-offset: 3px;
}
code { font: .9em ui-monospace, monospace; overflow-wrap: anywhere; }
.runs { color: #425a56; }
.overview { display: flex; flex-wrap: wrap; gap: .7rem; margin: 1.75rem 0; }
.overview a {
  display: flex; align-items: baseline; flex-wrap: wrap; gap: .45rem; padding: .55rem .85rem;
  background: #e4f1ee; border-radius: .45rem;
}
.count { font-size: 1.25rem; font-weight: 700; font-variant-numeric: tabular-nums; }
section { margin-top: 2rem; }
.table-scroll { overflow-x: auto; background: white; border: 1px solid #c6d7d3; }
table { width: 100%; border-collapse: collapse; text-align: left; }
caption { text-align: left; padding: .65rem .8rem; font-weight: 650; }
th, td { padding: .65rem .8rem; border-top: 1px solid #dee8e5; vertical-align: top; }
thead th { background: #ebf3f1; font-weight: 650; }
tbody th { font-weight: 600; }
tr:target, tr:target th { background: #e4f1ee; }
details { background: white; border: 1px solid #c6d7d3; margin: .6rem 0; }
summary { cursor: pointer; padding: .65rem .8rem; overflow-wrap: anywhere; font-weight: 600; }
details > p { padding: 0 .8rem; }
details > .table-scroll { border-width: 1px 0 0; }
.detail { display: block; color: #425a56; }
.contributors, .contributors ul { margin: 0; padding-left: 1.1rem; }
.contributors li + li { margin-top: .3rem; }
"""


def _text(value):
    return "—" if value is None else escape(str(value))


def _code(value):
    return f"<code>{_text(value)}</code>"


def _cell(content, *, header=False):
    if header:
        return f'<th scope="row">{content}</th>'
    return f"<td>{content}</td>"


def _table(label, headers, rows):
    heading = "".join(f'<th scope="col">{escape(header)}</th>' for header in headers)
    return (
        f'<div class="table-scroll" tabindex="0" role="region" aria-label="{escape(label)}">'
        "<table>"
        f"<caption>{escape(label)}</caption>"
        f"<thead><tr>{heading}</tr></thead><tbody>{''.join(rows)}</tbody>"
        "</table></div>"
    )


def _call_link(anchors, run_id, call_id):
    if call_id is None:
        return _text(None)
    code = _code(call_id)
    target = anchors.get((run_id, call_id))
    return f'<a href="#{target}">{code}</a>' if target else code


def _calls_table(calls, anchors, show_run):
    if not calls:
        return "<p>No calls were recorded.</p>"
    rows = []
    for call in calls:
        run_id, call_id = call["run_id"], call["call_id"]
        operation, label = call["operation"], call["label"]
        name = _code(operation)
        if label and label != operation:
            name = f'{_text(label)}<span class="detail">{name}</span>'
        identity = _code(call_id)
        if show_run:
            identity += f'<span class="detail">{_code(run_id)}</span>'
        rows.append(
            f'<tr id="{anchors[(run_id, call_id)]}">'
            f"{_cell(name, header=True)}{_cell(identity)}"
            f"{_cell(_call_link(anchors, run_id, call['parent_call_id']))}"
            f"{_cell(_text(call['status']))}"
            f"{_cell(_text(call['observation_count']))}</tr>"
        )
    return _table(
        "Recorded calls",
        ("Operation", "Call ID", "Parent call", "Status", "Observations"),
        rows,
    )


def _service_tables(services, anchors):
    if not services:
        return "<p>No service requests were recorded.</p>"
    tables = []
    for service in services:
        rows = []
        for request in service["requests"]:
            call = _call_link(anchors, request["run_id"], request["call_id"])
            outcome = _text(request["outcome"])
            if request["error_type"]:
                outcome += f'<span class="detail">{_code(request["error_type"])}</span>'
            rows.append(
                f"<tr>{_cell(_text(request['method']), header=True)}"
                f"{_cell(_text(request['service_kind']))}{_cell(outcome)}"
                f"{_cell(_text(request['status_code']))}"
                f"{_cell(_text(request['elapsed_ms']))}{_cell(call)}</tr>"
            )
        caption = f"Requests to {service['url']}"
        table = _table(
            caption, ("Method", "Service", "Outcome", "HTTP", "Time (ms)", "Call"), rows
        )
        count = service["request_count"]
        noun = "request" if count == 1 else "requests"
        tables.append(
            f"<details><summary>{_code(service['url'])} · {_text(count)} {noun}"
            f"</summary>{table}</details>"
        )
    return "".join(tables)


def _knowledge_sources(sources):
    items = []
    for source in sources or ():
        source_id = (
            _code(source["resource_id"])
            if isinstance(source, dict) and "resource_id" in source
            else _code(source)
        )
        role = source.get("resource_role") if isinstance(source, dict) else None
        if role:
            source_id += f" ({_text(role)})"
        items.append(f"<li>{source_id}</li>")
    return f"<ul>{''.join(items)}</ul>" if items else ""


def _contributors(contributors):
    items = []
    for item in contributors:
        items.append(
            f"<li>{_code(item['provider'])} · {_code(item['source_edge_id'])}"
            f"{_knowledge_sources(item['sources'])}</li>"
        )
    return f'<ul class="contributors">{"".join(items)}</ul>' if items else _text(None)


def _edge_tables(merges, anchors):
    if not merges:
        return "<p>No provider merges were recorded.</p>"
    tables = []
    for merge in merges:
        rows = (
            f"<tr>{_cell(_code(edge_id), header=True)}"
            f"{_cell(_code(edge['retained_provider']))}"
            f"{_cell(_contributors(edge['contributors']))}</tr>"
            for edge_id, edge in merge["edges"].items()
        )
        table = _table(
            "Retained edges", ("Edge ID", "Retained provider", "Contributors"), rows
        )
        call = _call_link(anchors, merge["run_id"], merge["call_id"])
        policy = _code(merge["policy"])
        count = merge["edge_count"]
        noun = "edge" if count == 1 else "edges"
        tables.append(
            f"<details><summary>Merge {_code(merge['call_id'])} · {_text(count)} {noun}"
            f"</summary><p>Call {call} · Merge policy {policy}</p>{table}</details>"
        )
    return "".join(tables)


def render_page(events) -> str:
    """Render the trace, provider outcomes and edge provenance as standalone HTML."""
    from .views import edges, providers, trace

    call_view, service_view, edge_view = trace(events), providers(events), edges(events)
    calls, services, merges = (
        call_view["calls"],
        service_view["services"],
        edge_view["merges"],
    )
    anchors = {
        (call["run_id"], call["call_id"]): f"call-{index}"
        for index, call in enumerate(calls, 1)
    }
    run_ids = sorted({call["run_id"] for call in calls})
    run_label = "Run" if len(run_ids) == 1 else "Runs"
    runs = (
        f'<p class="runs">{run_label} {", ".join(map(_code, run_ids))}</p>'
        if run_ids
        else ""
    )
    edge_count = sum(merge["edge_count"] for merge in merges)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy"
        content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
  <title>Translator query evidence</title>
  <style>{_STYLE}</style>
</head>
<body>
  <main>
    <header>
      <h1>Translator query evidence</h1>
      {runs}
    </header>
    <nav class="overview" aria-label="Report sections">
      <a href="#calls"><span class="count">{_text(call_view["call_count"])}</span> Calls</a>
      <a href="#providers"><span class="count">{_text(service_view["request_count"])}</span> Service requests</a>
      <a href="#edges"><span class="count">{_text(edge_count)}</span> Retained edges</a>
    </nav>
    <section id="calls" aria-labelledby="calls-heading">
      <h2 id="calls-heading">Calls</h2>
      {_calls_table(calls, anchors, len(run_ids) > 1)}
    </section>
    <section id="providers" aria-labelledby="providers-heading">
      <h2 id="providers-heading">Service requests</h2>
      {_service_tables(services, anchors)}
    </section>
    <section id="edges" aria-labelledby="edges-heading">
      <h2 id="edges-heading">Merged edge provenance</h2>
      {_edge_tables(merges, anchors)}
    </section>
  </main>
</body>
</html>
"""
