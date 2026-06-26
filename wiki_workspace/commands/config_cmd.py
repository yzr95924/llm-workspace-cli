"""llmw config <name> show|get|set|unset（spec §3.6）。"""

from wiki_workspace import errors, manifest, workspace
from wiki_workspace.commands import _common

REQUIRED = manifest.REQUIRED_KEYS  # path, display_name, created
SETTABLE = manifest.SETTABLE_KEYS  # display_name, description, model, tags


def _coerce(key, value):
    if key == "tags":
        return [t.strip() for t in str(value).split(",") if t.strip()]
    return value


def run(args):
    try:
        m = _common.load_manifest(args)
        root = _common.resolve_root(args)
    except errors.CommandError as exc:
        return exc.exit_code

    name = args.name
    if name not in m.wikis:
        errors.emit_error("wiki-not-found", "wiki '{}' 不存在".format(name), hint="llmw list")
        return errors.EXIT_USER_ERROR
    w = m.wikis[name]

    if args.action == "show":
        print("name:          {}".format(name))
        print("path:          {}".format(w.path))
        print("display_name:  {}".format(w.display_name))
        print("description:   {}".format(w.description))
        print("model:         {}".format(w.effective_model(m.default_model)))
        print("created:       {}".format(w.created))
        print("tags:          {}".format(", ".join(w.tags)))
        return errors.EXIT_OK

    if args.action == "get":
        if args.key in ("display_name", "description", "model", "created"):
            val = (
                getattr(w, args.key) if args.key != "model" else w.effective_model(m.default_model)
            )
            print(val if val is not None else "")
        elif args.key == "tags":
            print(",".join(w.tags))
        elif args.key == "path":
            print(w.path)
        else:
            errors.emit_error("invalid-config-key", "未知 key '{}'".format(args.key))
            return errors.EXIT_ENV_ERROR
        return errors.EXIT_OK

    if args.action == "set":
        if args.key not in SETTABLE:
            errors.emit_error(
                "invalid-config-key",
                "key '{}' 不可 set（允许：{}）".format(args.key, ", ".join(sorted(SETTABLE))),
            )
            return errors.EXIT_ENV_ERROR
        setattr(w, args.key, _coerce(args.key, args.value))
        workspace.save_manifest(root, m)
        print("Set wikis.{}.{} = {}".format(name, args.key, args.value))
        return errors.EXIT_OK

    if args.action == "unset":
        if args.key in REQUIRED or args.key not in SETTABLE:
            errors.emit_error(
                "invalid-config-key", "key '{}' 不可 unset（必填或非法）".format(args.key)
            )
            return errors.EXIT_ENV_ERROR
        if args.key == "tags":
            w.tags = []
        elif args.key == "description":
            w.description = ""
        elif args.key == "model":
            w.model = None
        workspace.save_manifest(root, m)
        print("Unset wikis.{}.{}".format(name, args.key))
        return errors.EXIT_OK

    return errors.EXIT_INTERNAL  # 不可达（argparse 已约束 action）
