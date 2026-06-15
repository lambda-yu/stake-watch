from stake_watch.storage.config_store import ConfigStore
from stake_watch.storage.db import Storage

_storage: Storage | None = None
_config_store: ConfigStore | None = None

def init_deps(storage: Storage):
    global _storage, _config_store
    _storage = storage
    _config_store = ConfigStore(storage._session_factory)

def get_config_store() -> ConfigStore:
    assert _config_store is not None
    return _config_store

def get_storage() -> Storage:
    assert _storage is not None
    return _storage
