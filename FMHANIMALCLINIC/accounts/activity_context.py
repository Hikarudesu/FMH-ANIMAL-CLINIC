"""Request-local actor context for model signal audit logging."""

from contextvars import ContextVar


_current_actor = ContextVar('current_actor', default=None)
_current_ip_address = ContextVar('current_ip_address', default=None)


def set_current_actor(actor):
    return _current_actor.set(actor)


def reset_current_actor(token):
    _current_actor.reset(token)


def get_current_actor():
    return _current_actor.get()


def set_current_ip_address(ip_address):
    return _current_ip_address.set(ip_address)


def reset_current_ip_address(token):
    _current_ip_address.reset(token)


def get_current_ip_address():
    return _current_ip_address.get()