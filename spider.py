import random
import string
import copy
import hashlib
from collections import deque
import time
import cProfile



show_game_won       = 0x0001    # print winning game
show_game_lost      = 0x0002    # print when game lost
show_game_seen      = 0x0004    # print when game seen before
show_stack_done     = 0x0010    # print when a stack moves to "done"
show_stat_all       = 0x0100    # print status (won/lost) every game
show_stat_some      = 0x0200    # print status (won/lost) periodically
show_move           = 0x1000    # print one line per move
show_move_game      = 0x2000    # print game after each move

show = show_game_won | show_stack_done | show_stat_some



class Deck:
    """Deck of cards"""

    def __init__(self, decks=1):
        self._cards = []
        while decks > 0:
            for s in 'SHCD':
                for v in range(1, 14):
                    self._cards.append((v, s))
            decks = decks - 1

    def shuffle(self):
        new = []
        while len(self._cards) > 0:
            new.append(self._cards.pop(random.randrange(len(self._cards))))
        self._cards = new

    def deal(self):
        return self._cards.pop()



# A card is a 2-tuple of the form (rank, suit), where rank = 1...13, and suit = S, H, C, or D
def card_name(c):
    """Map {1 ... 13} to {A 2 3 ... 9 10 J Q K}, plus suit, e.g. (1, 'S') returns 'AS'"""
    if len(c) != 2:
        return ''
    elif c[0] == 1:
        return 'A' + c[1]
    elif c[0] == 11:
        return 'J' + c[1]
    elif c[0] == 12:
        return 'Q' + c[1]
    elif c[0] == 13:
        return 'K' + c[1]
    else:
        return str(c[0]) + c[1]



# _down[0][4] _down[1][4] ... _down[3][4]
# _down[0][3] _down[1][3] ... _down[3][3] _down[4][3] ... _down[9][3]
# _down[0][2] _down[1][2] ... _down[3][2] _down[4][2] ... _down[9][2]
# _down[0][1] _down[1][1] ... _down[3][1] _down[4][1] ... _down[9][1]
# _down[0][0] _down[1][0] ... _down[3][0] _down[4][0] ... _down[9][0] (top)
#   _up[0][0]   _up[1][0] ...   _up[3][0]   _up[4][0] ...   _up[9][0]
#   _up[0][1]   _up[1][1] ...   _up[3][1]   _up[4][1] ...   _up[9][1] (top)
#
# _moves is the list of moves that gets a game into its state. It is append-
# only; nothing is ever inserted or deleted. It can get very long (thousands),
# such that copying games becomes a memory issue. As a memory optimization,
# it is stored as a list of lists, i.e. moves are appended to the last list
# in _moves, and when it gets to a certain length, a new list is added to
# _moves and it is filled. That makes it so a shallow copy of _moves is
# almost sufficient when copying games - the lists in _moves that are full
# can be simply referred to, but the last list that is still receiving moves
# must be actually copied.
#
class SpiderGame():
    """One game of spider solitaire"""

    def __init__(self, cards=None):
        # Initial state
        self._moves = [[]]
        self._moves_max = 100
        self._done = []
        self._down = [[], [], [], [], [], [], [], [], [], []]
        self._up = [[], [], [], [], [], [], [], [], [], []]
        self._pile = []
        self._next = (0, 0) # next move to consider: (src, dst)
        if not cards is None:
            # deal 4 to each of ten down stacks
            for i in range(4):
                for s in self._down:
                    s.insert(0, cards.pop())
            # deal 1 more to first four down stacks
            for i in range(4):
                self._down[i].insert(0, cards.pop())
            # 1 card to each up stack
            for s in self._up:
                s.append(cards.pop())
            # pile has remaining cards (50)
            for s in range(50):
                self._pile.append(cards.pop())

    def _invariant(self):
        """Check that current game structure is consistent"""
        count = 0
        assert len(self._done) <= 8     # up to 8 stacks
        for s in self._done:
            assert len(s) == 13         # each exactly 13 cards
            count = count + 13
        assert len(self._down) == 10    # always 10 down stacks
        for s in self._down:
            assert len(s) <= 5          # never more than 5 on a down stack
            count = count + len(s)
        assert len(self._up) == 10      # always 10 up stacks
        for s in self._up:
            count = count + len(s)      # up stacks can be "arbitrary" length
        assert len(self._pile) <= 50    # pile starts at 50 and shrinks
        assert (len(self._pile) % 10) == 0  # pile always a multiple of 10
        count = count + len(self._pile)
        assert count == 104             # always 104 cards total in the game

    def copy(self):
        c = SpiderGame()
        # done stacks: the stacks are immutable (once they are done),
        # but the list of stacks is not
        for s in self._done:
            c._done.append(s)
        # down, up, pile stacks: stacks are mutable, cards are immutable
        c._down = []
        for s in self._down:
            c._down.append(copy.copy(s))
        c._up = []
        for s in self._up:
            c._up.append(copy.copy(s))
        c._pile = copy.copy(self._pile)
        # next move: copy the tuple
        c._next = copy.copy(self._next)
        # moves: copy the top-level list and the last list it contains
        # all lists in _moves except the last are immutable
        c._moves = copy.copy(self._moves)
        c._moves[-1] = copy.copy(self._moves[-1])
        return c

    def deal_from_pile(self):
        """Deal from pile to up cards"""
        self._invariant()
        if len(self._pile) == 0:
            return False
        for s in self._up:
            s.append(self._pile.pop(0))
        self._next = (0, 0)
        self._moves[-1].append('Deal')
        if len(self._moves[-1]) == self._moves_max:
            self._moves.append([])
        self._invariant()
        return True

    def get_hash(self):
        """Return a hash of the current game"""
        # state does not include _moves or _next
        # state does include _done, but it is implied from the others
        h = hashlib.md5()
        # down cards
        for s in self._down:
            h.update('*')
            for c in s:
                h.update(str(c[0]))
                h.update(c[1])
        # up cards
        for s in self._up:
            h.update('*')
            for c in s:
                h.update(str(c[0]))
                h.update(c[1])
        # pile
        h.update('*')
        for c in self._pile:
            h.update(str(c[0]))
            h.update(c[1])
        return h.hexdigest()

    def print_game(self):
        # done stacks
        print '=================================================='
        for s in self._done:
            for c in s:
                print c,
            print
        # down cards
        print '--------------------------------------------------'
        for row in range(4, -1, -1):  # 4...0
            for s in self._down:
                if len(s) > row:
                    print string.rjust(card_name(s[row]), 4),
                else:
                    print string.rjust(card_name(()), 4),
            print
        # up cards
        print '--------------------------------------------------'
        num_rows = 0
        for s in self._up:
            if num_rows < len(s):
                num_rows = len(s)
        for row in range(num_rows):
            for s in self._up:
                if len(s) > row:
                    print string.rjust(card_name(s[row]), 4),
                else:
                    print string.rjust(card_name(()), 4),
            print
        print '--------------------------------------------------'
        # pile
        for c in self._pile:
            print card_name(c),
        print
        print '=================================================='
        # next move
        #print 'Next:', self._next[0], '->', self._next[1]

    def _find_longest(self, stack):
        """Find the number of cards a the end of stack that are a valid move"""
        L = len(stack)
        # if there are 0 or 1 cards on the stack, that's the answer
        if L < 2:
            return L
        num = 2
        while True:
            # If 'num' cards is an invalid move, then 'num'-1 is the answer.
            if stack[-num][0] != stack[-(num - 1)][0] or stack[-num][1] != stack[-(num - 1)][1]:
                return num - 1
            # If the stack is 'num' cards in length, 'num' is the answer.
            if num == L:
                return num;
            # The stack has more than 'num' cards; see if one more is still valid.
            num = num + 1

    def next_move(self):
        src = self._next[0]
        dst = self._next[1]
        dst = dst + 1
        if dst >= 10:
            src = src + 1 # src=10 means no more moves (time to deal)
            dst = 0
        self._next = (src, dst)

    def _move_cards(self, src, dst, numCards):
        """Move cards (internal function)"""
        self._up[dst].extend(self._up[src][-numCards:])
        self._up[src][-numCards:] = []
        self._moves[-1].append((src, dst))
        if len(self._moves[-1]) == self._moves_max:
            self._moves.append([])
        self._next = (0, 0)
        # see if we need to flip a down card
        if len(self._up[src]) == 0:
            if len(self._down[src]) > 0:
                # is this a card we don't know yet?
                if self._down[src][0][0] == 0:
                    print 'Got to unknown card!'
                    self.print_game()
                    print 'Moves:', self._moves
                    assert False
                self._up[src].append(self._down[src][0])
                self._down[src][0:1] = []
        # see if we finished a stack
        if self._find_longest(self._up[dst]) == 13:
            self._done.append(self._up[dst][-13:0])
            self._up[dst][-13:0] = []
            if show & show_stack_done:
                self.print_game()

    def move(self, do_move=True):
        """Determine whether cards can move from _up[src] to _up[dst]"""
        #
        src = self._next[0]
        dst = self._next[1]
        up_src = self._up[src]
        up_dst = self._up[dst]
        #
        # if there are no cards in the src stack, return False (no move possible)
        if len(up_src) == 0:
            # the only way there are no up cards is if there are no down cards
            assert len(self._down[src]) == 0
            if do_move:
                self._next = (0, 0)
            return False
        #
        # if dst stack is empty, then we can move the longest sequence from src
        if len(up_dst) == 0:
            assert len(self._down[dst]) == 0
            cardsToMove = self._find_longest(up_src)
            assert cardsToMove >= 1 and cardsToMove <= len(up_src)
            if do_move:
                self._move_cards(src, dst, cardsToMove)
            return True
        #
        cardsToMove = 1
        while True:
            # If the numeric value of the card "cardsToMove" from the top in
            # src is one less than the numeric value of the topmost card in
            # dst, then the move is legal.
            if up_src[-cardsToMove][0] == (up_dst[-1][0] - 1):
                # Can move it! Stop searching for longer movable stacks from
                # up_src, since it is not possible to extend what we have on
                # up_src and also be a valid move to up_dst.
                if do_move:
                    self._move_cards(src, dst, cardsToMove)
                return True
            cardsToMove = cardsToMove + 1
            if cardsToMove > len(up_src):
                # tried all moves from src; none are a legal move
                if do_move:
                    self._next = (0, 0)
                return False
            card1 = up_src[-cardsToMove]  # one deeper in stack
            card2 = up_src[-cardsToMove + 1]  # card on top of it
            # deeper card must be one less, and must be same suit
            if (card1[0] != (card2[0] + 1)) or (card1[1] != card2[1]):
                # next longer move on up_src is not valid
                if do_move:
                    self._next = (0, 0)
                return False

stat_some_time = 0

class Spider4():

    def __init__(self, game):
        self._games = deque([])
        self._hashes = []
        for h in range(256):
            self._hashes.append([])
        self._games.append(game)
        self.total_hashes = 0
        self._hash_add(game.get_hash())
        self.won = 0
        self.lost = 0
    # end __init__

    def _hash_add(self, h):
        i = int(h[:2], 16)
        self._hashes[i].append(h)
        self.total_hashes = self.total_hashes + 1

    def _hash_find(self, h):
        i = int(h[:2], 16)
        if h in self._hashes[i]:
            return True
        else:
            return False

    def play(self):
        pr = cProfile.Profile()
        pr.enable()
        stat_interval = 10000
        stat_some = stat_interval
        stat_some_time = time.time()
        while len(self._games) > 0:
            # continue next game in queue
            if show & show_stat_all:
                print '{0} won, {1} lost, {2} in progress'.format(self.won, self.lost, len(self._games))
            elif show & show_stat_some:
                stat_some = stat_some - 1
                if stat_some == 0:
                    print '{0:0.1f}: {1} won, {2} lost, {3} in progress'.format(time.time() - stat_some_time, self.won, self.lost, len(self._games))
                    stat_some = stat_interval
                    stat_some_time = time.time()
                    #pr.print_stats()
                    pr = cProfile.Profile()
                    pr.enable()
            game = self._games.pop()
            if show & show_move_game:
                print 'RESUME'
                game.print_game()
            pass
            while True:
                src = game._next[0]
                dst = game._next[1]
                if dst == src:
                    game.next_move()
                    continue
                if src < 10:
                    if game.move(False):
                        # game without taking this move goes on the to-do list
                        game2 = game.copy() # copy.deepcopy(game)
                        game2.next_move()
                        self._games.append(game2)
                        # continue playing the game where we take the move
                        if show & show_move:
                            print 'MOVE:', game._next[0], '->', game._next[1]
                        game.move(True)
                        if len(game._done) == 8:
                            if show & show_game_won:
                                print 'WINNER'
                                print game._moves
                            self.won = self.won + 1
                            break # while True
                        h = game.get_hash()
                        if self._hash_find(h):
                            # seen this one
                            if show & show_game_seen:
                                print 'SEEN IT'
                            break # while True
                        self._hash_add(h)
                        if show & show_move_game:
                            game.print_game()
                    else: # can't make current move
                        game.next_move()
                else: # src >= 10
                    # out of moves - deal
                    if not game.deal_from_pile():
                        # out of cards, loser
                        if show & show_game_lost:
                            print 'LOSE'
                        self.lost = self.lost + 1
                        break
                    if show & show_move:
                        print 'DEAL'
                    if show & show_move_game:
                        game.print_game()
            # end while True
        # end while len()
        pass
    # end play()



#random.seed(0)
#decks = Deck(2)
#decks.shuffle()
#s = SpiderGame(decks)
#g = Spider4(s)
#g.play()
#pass

# game that is known winnable
cards = [
     (9, 'S'), (12, 'D'),  (1, 'S'),  (7, 'H'),  (9, 'D'),  (4, 'H'),  (9, 'C'),  (5, 'D'),  (6, 'C'), (11, 'C'),
    (12, 'S'),  (6, 'S'),  (4, 'C'),  (7, 'C'), (11, 'H'),  (6, 'D'),  (7, 'S'),  (9, 'D'),  (9, 'C'),  (4, 'D'),
     (3, 'C'), (10, 'C'),  (5, 'H'),  (3, 'S'),  (5, 'C'),  (2, 'S'), (10, 'H'),  (3, 'D'), (10, 'H'),  (2, 'S'),
     (3, 'S'), (13, 'H'),  (2, 'D'),  (7, 'H'), (10, 'C'), (13, 'D'),  (8, 'S'), (12, 'H'),  (2, 'D'), (11, 'D'),
    (13, 'H'), (11, 'S'),  (5, 'D'), (13, 'D'),

    (12, 'H'),  (6, 'H'),  (4, 'C'),  (2, 'C'), (10, 'D'),  (8, 'S'),  (8, 'D'), (13, 'S'),  (6, 'H'), (13, 'C'),

     (1, 'C'),  (5, 'H'),  (8, 'H'),  (4, 'S'),  (7, 'C'),  (1, 'C'),  (2, 'H'),  (5, 'C'), (10, 'S'),  (1, 'H'),
     (7, 'D'),  (3, 'H'),  (8, 'C'),  (5, 'S'), (11, 'H'),  (6, 'D'),  (4, 'H'),  (2, 'H'), (11, 'S'), (12, 'S'),
     (7, 'S'),  (3, 'C'),  (6, 'S'),  (8, 'C'),  (8, 'H'),  (9, 'H'),  (8, 'D'),  (1, 'D'), (13, 'C'),  (6, 'C'),
     (3, 'H'), (12, 'C'),  (5, 'S'),  (3, 'D'),  (9, 'H'), (10, 'D'), (10, 'S'), (12, 'C'),  (4, 'D'), (11, 'D'),
     (7, 'D'),  (9, 'S'),  (1, 'H'),  (4, 'S'), (12, 'D'),  (2, 'C'), (13, 'S'),  (1, 'S'), (11, 'C'),  (1, 'D'),
    ]

# winnability unknown
# cards = [
#     (10, 'S'),  (2, 'C'),  (0, 'X'),  (8, 'H'),  (9, 'D'),  (0, 'X'),  (8, 'D'),  (9, 'C'), (11, 'H'), (10, 'H'),
#     (11, 'D'), (13, 'C'),  (0, 'X'),  (7, 'S'), (10, 'D'),  (0, 'X'),  (8, 'C'),  (2, 'S'),  (7, 'D'),  (8, 'S'),
#     (10, 'H'),  (6, 'S'), (13, 'D'),  (5, 'C'),  (7, 'C'), (13, 'D'),  (5, 'H'), (13, 'S'), (13, 'H'), (11, 'C'),
#      (2, 'C'), (13, 'S'),  (4, 'C'),  (1, 'C'),  (3, 'H'), (12, 'H'),  (2, 'D'),  (5, 'C'),  (2, 'H'), (11, 'D'),
#      (9, 'H'),  (6, 'C'),  (4, 'S'),  (3, 'C'),
# 
#      (6, 'H'), (10, 'D'),  (6, 'D'), (12, 'H'), (13, 'H'),  (6, 'S'), (12, 'C'),  (5, 'S'),  (5, 'S'),  (6, 'H'),
# 
#      (4, 'D'), (12, 'S'), (13, 'C'), (12, 'D'),  (2, 'S'),  (4, 'H'),  (4, 'D'),  (8, 'D'),  (2, 'H'),  (4, 'S'),
#      (1, 'S'),  (7, 'H'), (11, 'S'),  (8, 'S'),  (3, 'H'),  (5, 'D'),  (3, 'D'), (12, 'D'),  (9, 'S'),  (5, 'H'),
#      (9, 'D'),  (9, 'H'),  (1, 'C'),  (5, 'D'), (11, 'H'),  (1, 'S'),  (7, 'D'),  (1, 'D'),  (6, 'C'),  (1, 'H'),
#     (12, 'S'),  (8, 'H'),  (9, 'C'),  (2, 'D'),  (4, 'C'),  (3, 'C'),  (1, 'D'),  (9, 'S'), (10, 'C'), (10, 'S'),
#      (6, 'D'),  (3, 'S'),  (3, 'S'),  (4, 'H'), (10, 'C'),  (8, 'C'), (12, 'C'), (11, 'C'),  (3, 'D'),  (7, 'S')
#     ]
cards.reverse()
s = SpiderGame(cards)
s.print_game()
g = Spider4(s)
g.play()
pass
