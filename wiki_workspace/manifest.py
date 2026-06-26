"""manifest 内存模型 + parse/serialize。纯模块：不碰文件系统、不碰 errors。"""

from typing import Dict

DEFAULT_MODEL = "claude-sonnet-4-6"
SCHEMA_VERSION = "1"


class WikiEntry:
    def __init__(self, name, path, display_name, created, description="", model=None, tags=None):
        self.name = name
        self.path = path
        self.display_name = display_name
        self.description = description or ""
        self.model = model  # None => 继承 workspace.default_model
        self.created = created
        self.tags = list(tags or [])

    def effective_model(self, default_model):
        return self.model if self.model else default_model

    def to_dict(self):
        d = {
            "path": self.path,
            "display_name": self.display_name,
            "created": self.created,
            "tags": list(self.tags),
        }
        if self.description:
            d["description"] = self.description
        if self.model:
            d["model"] = self.model
        return d


class Manifest:
    def __init__(self, schema_version, created, default_model, wikis):
        self.schema_version = schema_version
        self.created = created
        self.default_model = default_model
        self.wikis = wikis  # Dict[str, WikiEntry]（保持插入顺序）

    def to_dict(self):
        return {
            "schema_version": self.schema_version,
            "created": self.created,
            "workspace": {"default_model": self.default_model},
            "wikis": {name: w.to_dict() for name, w in self.wikis.items()},
        }


def empty_manifest(created, default_model=DEFAULT_MODEL):
    return Manifest(SCHEMA_VERSION, created, default_model, {})


def parse(text):
    """把 TOML 文本解析成 Manifest。语法错误时抛 tomllib.TOMLDecodeError
    （调用方映射为 manifest-parse-failed）。未知字段在此忽略；
    语义校验放在 validate()。"""
    try:
        import tomllib  # py>=3.11
    except ModuleNotFoundError:  # pragma: no cover
        import tomli as tomllib  # type: ignore
    data = tomllib.loads(text)

    ws = data.get("workspace", {})
    default_model = ws.get("default_model", DEFAULT_MODEL)

    wikis: Dict[str, WikiEntry] = {}
    for name, w in data.get("wikis", {}).items():
        wikis[name] = WikiEntry(
            name=name,
            path=w.get("path", ""),
            display_name=w.get("display_name", name),
            created=w.get("created", ""),
            description=w.get("description", ""),
            model=w.get("model"),
            tags=w.get("tags", []),
        )
    return Manifest(
        schema_version=data.get("schema_version", SCHEMA_VERSION),
        created=data.get("created", ""),
        default_model=default_model,
        wikis=wikis,
    )


def serialize(m):
    """把 Manifest 转 TOML，经 workspace.dump_toml（惰性 import，保持 manifest
    在 import 期为纯模块——无环，因为 workspace 只 import errors）。"""
    from wiki_workspace.workspace import dump_toml

    return dump_toml(m.to_dict())
