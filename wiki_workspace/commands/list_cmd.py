"""llmw list — 列出 wiki（spec §3.2）。"""

from wiki_workspace import errors
from wiki_workspace.commands import _common


def _row(name, w, default_model):
    return {
        "name": name,
        "path": w.path,
        "display_name": w.display_name,
        "model": w.effective_model(default_model),
        "tags": list(w.tags),
        "created": w.created,
    }


def run(args):
    try:
        m = _common.load_manifest(args)
    except errors.CommandError as exc:
        if args.json:
            print(
                errors.render_json_result(
                    exc.exit_code, [errors.ErrorRecord(exc.category, exc.message, exc.hint)]
                )
            )
        return exc.exit_code

    rows = [_row(n, w, m.default_model) for n, w in m.wikis.items()]
    if getattr(args, "tag", None):
        rows = [r for r in rows if args.tag in r["tags"]]

    if getattr(args, "json", False):
        print(errors.render_json_result(errors.EXIT_OK, result={"wikis": rows}))
        return errors.EXIT_OK

    if not rows:
        print("（无 wiki）")
        return errors.EXIT_OK

    print("{:<18} {:<20} {:<22} {:<18} {}".format("NAME", "PATH", "MODEL", "TAGS", "CREATED"))
    for r in rows:
        print(
            "{:<18} {:<20} {:<22} {:<18} {}".format(
                r["name"], r["path"] + "/", r["model"], ",".join(r["tags"]), r["created"]
            )
        )
    return errors.EXIT_OK
