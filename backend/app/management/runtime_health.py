"""Read-only native evidence. Management polling never supplies a JS probe or business authority."""
import time

PAGE_SAMPLE_SECONDS = 45
MANAGEMENT_ONLINE_SECONDS = 60


def management_online(last_seen, now=None):
    elapsed = (time.time() if now is None else now) - last_seen
    return 0 <= elapsed < MANAGEMENT_ONLINE_SECONDS


def page_health(metadata, last_seen, now=None):
    value = {'state': 'unknown', 'error': '', 'age_seconds': None, 'page_release': '',
             'terminal_state': 'unknown', 'webview': '', 'light_state': 'unknown'}
    runtime = metadata.get('runtime')
    if not runtime:
        return value
    elapsed = (time.time() if now is None else now) - last_seen
    native_age = runtime.get('page_age_seconds')
    age = native_age + elapsed if native_age is not None and elapsed >= 0 else None
    value.update(error=runtime.get('page_error', ''), age_seconds=int(age) if age is not None else None,
                 page_release=runtime.get('page_release', ''), terminal_state=runtime.get('terminal_state', 'unknown'),
                 webview=runtime.get('webview', ''), light_state=runtime.get('light_state', 'unknown'))
    state = runtime.get('page_state', 'waiting')
    if not 0 <= elapsed < MANAGEMENT_ONLINE_SECONDS:
        state = 'offline'
    elif state == 'ready':
        state = 'unknown' if age is None else 'stale' if age >= PAGE_SAMPLE_SECONDS else 'ready'
    value['state'] = state
    return value
