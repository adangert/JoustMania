"""Shared next-pairing selection for the menu and debug web process."""
import time


def initialize(ns, manager):
    ns.pairing_state = manager.dict(layout=[], reservations={}, override='', cursor='', busy=False, error='', refreshed=0.0)
    ns.pairing_lock = manager.RLock()


def read_layout():
    import dbus
    import jm_dbus
    import psmove_dbus
    bus = jm_dbus.ensure_process_bus()
    if not bus.name_has_owner(jm_dbus.ORG_BLUEZ):
        raise RuntimeError('Bluetooth service is unavailable')
    objects = dbus.Interface(bus.get_object(jm_dbus.ORG_BLUEZ, '/'),
                             'org.freedesktop.DBus.ObjectManager').GetManagedObjects(timeout=1)
    layout = []
    for path, interfaces in objects.items():
        adapter = interfaces.get('org.bluez.Adapter1')
        if not adapter or not adapter.get('Powered'):
            continue
        connected = []
        for device_path, device_interfaces in objects.items():
            device = device_interfaces.get('org.bluez.Device1', {})
            if str(device_path).startswith(str(path) + '/') and device.get('Connected') and psmove_dbus.is_psmove_device(device):
                connected.append(str(device['Address']).upper())
        layout.append(dict(name=str(path).rsplit('/', 1)[-1], address=str(adapter['Address']).upper(), connected=connected))
    return sorted(layout, key=lambda a: (int(a['name'][3:]), a['address']))


def refresh(ns, force=False):
    state, lock = ns.pairing_state, ns.pairing_lock
    with lock:
        if state['busy'] or (not force and time.monotonic() - state['refreshed'] < 1):
            return
        try:
            layout = read_layout()
        except Exception as error:
            state['error'] = str(error)
            state['refreshed'] = time.monotonic()
            return
        state['layout'] = layout
        state['refreshed'] = time.monotonic()
        state['error'] = ''
        if state['override'] and state['override'] not in {a['address'] for a in layout}:
            state['override'] = ''


def describe(state):
    reservations = dict(state['reservations'])
    adapters = []
    for adapter in state['layout']:
        members = set(adapter['connected'])
        # A later USB pairing supersedes a previous assignment for that serial.
        members = {serial for serial in members if reservations.get(serial, adapter['address']) == adapter['address']}
        members.update(serial for serial, address in reservations.items() if address == adapter['address'])
        adapters.append(dict(name=adapter['name'], address=adapter['address'], count=len(members)))
    automatic = next((a['address'] for a in adapters if a['count'] < 5), '')
    if adapters and not automatic:
        addresses = [a['address'] for a in adapters]
        cursor = state['cursor']
        automatic = addresses[(addresses.index(cursor) + 1) % len(addresses)] if cursor in addresses else addresses[0]
    override = state['override']
    return dict(available=True, adapters=adapters, automatic=automatic,
                selected=override or automatic, override=override, busy=state['busy'], error=state['error'])


def status(ns):
    if not hasattr(ns, 'pairing_state'):
        return dict(available=False, adapters=[], selected='', automatic='', override='', busy=False, error='')
    refresh(ns)
    with ns.pairing_lock:
        return describe(ns.pairing_state)


def select(ns, address):
    refresh(ns, force=True)
    with ns.pairing_lock:
        state = ns.pairing_state
        if state['busy']:
            raise ValueError('A pairing is already in progress. Try again after it finishes.')
        if state['error']:
            raise ValueError(state['error'])
        if address and address not in {a['address'] for a in state['layout']}:
            raise ValueError('That adapter is no longer available.')
        state['override'] = address
        return describe(state)


def begin(ns):
    refresh(ns, force=True)
    with ns.pairing_lock:
        state = ns.pairing_state
        target = describe(state)['selected']
        if state['busy'] or state['error'] or not target:
            return ''
        state['busy'] = True
        return target


def finish(ns, serial, target, succeeded):
    with ns.pairing_lock:
        state = ns.pairing_state
        if succeeded:
            reservations = dict(state['reservations'])
            reservations[serial.upper()] = target
            state['reservations'] = reservations
            state['cursor'] = target
            state['override'] = ''
            state['error'] = ''
        state['busy'] = False
        # Keep the successful reservation even before BlueZ publishes the link.
        state['refreshed'] = 0.0
