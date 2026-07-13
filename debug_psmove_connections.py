#!/usr/bin/env python3
"""Print PS Move registrations known to BlueZ."""

import psmove_dbus


def yes_no(value):
    return 'yes' if value else 'no'


def main():
    controllers = psmove_dbus.get_registered_controllers()
    if not controllers:
        print('No PS Move controllers are registered with BlueZ')
        return

    header = '{:<7} {:<17} {:<17} {:<5} {:<10} {:<7} {:<12} {:<9} {:<7}'.format(
        'HCI', 'Adapter', 'Controller', 'Model', 'Registered', 'Loaded',
        'BlueZ Paired', 'Connected', 'Trusted'
    )
    print(header)
    print('-' * len(header))
    for controller in controllers:
        display = dict(controller)
        display['registered'] = yes_no(controller['registered'])
        display['loaded'] = yes_no(controller['loaded'])
        display['paired'] = yes_no(controller['paired'])
        display['connected'] = yes_no(controller['connected'])
        display['trusted'] = yes_no(controller['trusted'])
        print('{adapter:<7} {adapter_address:<17} {address:<17} {model:<5} '
              '{registered:<10} {loaded:<7} {paired:<12} {connected:<9} '
              '{trusted:<7}'.format(
                  **display
              ))
    print('\n{} PS Move controller registration(s)'.format(len(controllers)))


if __name__ == '__main__':
    main()
