"""Resolve a series reply to one instance; zero must never mean the whole series."""


def is_recurring(occurrence, events):
    return occurrence.original_time > 0 or any(
        e.uid == occurrence.uid and e.start_time != occurrence.start_time for e in events)


def recurring_time(occurrence, events):
    if not is_recurring(occurrence, events):
        raise ValueError('Recurring instance evidence missing')
    # Positive original_time is the original start of an exception, not its moved start.
    value = occurrence.original_time or int(occurrence.start_time.timestamp())
    if value <= 0 or int(value) != value or occurrence.start_time.tzinfo is None:
        raise ValueError('Invalid recurring instance time')
    return int(value)


def release_target(record, occurrence, events):
    if record.get('release_scope') == 'recurring_instance':
        original = recurring_time(occurrence, events)
        if record.get('release_original_time') != original:
            raise ValueError('Recurring instance changed')
        return occurrence.model_copy(update={'original_time': original})
    if is_recurring(occurrence, events):
        raise ValueError('Series cannot use non-recurring release')
    return occurrence
