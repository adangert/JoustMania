import psmove

def get_move(serial, move_num):
    move = psmove.PSMove(move_num)
    if move.get_serial() != serial:
        for move_num in range(psmove.count_connected()):
            move = psmove.PSMove(move_num)
            if move.get_serial() == serial:
                return move
        return None
    else:
        return move
