import sys
import random
import string
import copy
import hashlib

sys.setrecursionlimit(10000)

verbosity = 2


class Deck:
    """Deck of cards"""

    def __init__(self, decks=1):
        self._cards = []
        while decks > 0:
            for s in 'SHCD':
                for v in range(1, 14):
                    self._cards.append((v, s))
            decks = decks - 1

    def deal(self):
        return self._cards.pop(random.randrange(len(self._cards)))



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
class Spider4():
    """One game of 4-suit spider"""

    # Class Variables

    # list of hashes of games seen so far when playing
    _seen = []

    def __init__(self):
        self._nest = 0
        self.deal_new()

    def invariant(self):
        """Check that current game structure is consistent"""
        count = 0
        assert len(self._done) <= 8
        for s in self._done:
            assert len(s) == 13
            count = count + 13
        assert len(self._down) == 10
        for s in self._down:
            assert len(s) <= 5
            count = count + len(s)
        assert len(self._up) == 10
        for s in self._up:
            count = count + len(s)
        assert len(self._pile) <= 50
        assert (len(self._pile) % 10) == 0
        count = count + len(self._pile)
        assert count == 104

    def deal_new(self):
        """Deal a new game"""
        self._done = []
        self._down = [[], [], [], [], [], [], [], [], [], []]
        self._up = [[], [], [], [], [], [], [], [], [], []]
        self._pile = []
        self._moves = []
        # 2 decks in spider-4
        d = Deck(2)
        # deal 4 to each down stack
        for i in range(4):
            for s in self._down:
                s.append(d.deal())
        # deal 1 more to first 4 down stacks
        for i in range(4):
            self._down[i].append(d.deal())
        # 1 card to each up stack
        for s in self._up:
            s.append(d.deal())
        # pile has 50
        for s in range(50):
            self._pile.append(d.deal())

    def deal_one(self):
        """Deal one row of ten cards"""
        self.invariant()
        if len(self._pile) == 0:
            return False
        for s in self._up:
            s.append(self._pile[0])
            self._pile[:1] = []
        self._moves.append('Deal')
        self.invariant()
        return True

    def get_hash(self):
        """Return a hash of the current game"""
        h = hashlib.md5()
        # down cards
        for s in self._down:
            h.update('*')
            for c in s:
                h.update(card_name(c))
        # up cards
        for s in self._up:
            h.update('*')
            for c in s:
                h.update(card_name(c))
        # pile
        h.update('*')
        for c in self._pile:
            h.update(card_name(c))
        return h.hexdigest()

    def print_table(self):
        # done stacks
        for s in self._done:
            print 'Done:',
            for c in s:
                print c,
            print
        # down cards
        print 'Down:'
        for row in range(4, -1, -1):  # 4...0
            for col in range(10):
                if len(self._down[col]) > row:
                    print string.rjust(card_name(self._down[col][row]), 4),
                else:
                    print string.rjust(card_name(()), 4),
            print
        # up cards
        print 'Up:'
        row = 0
        done = False
        while not done:
            done = True
            for col in range(10):
                if len(self._up[col]) > row:
                    print string.rjust(card_name(self._up[col][row]), 4),
                    done = False
                else:
                    # this causes a blank line the last time through
                    print string.rjust(card_name(()), 4),
            print
            row = row + 1
        # pile
        print 'Pile:'
        for c in self._pile:
            print card_name(c),
        print

    def find_tail(self, stack):
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

    def move(self, col1, col2, doMove=True):
        """Determine whether cards can move from _up[col1] to _up[col2]"""
        up1 = self._up[col1]
        up2 = self._up[col2]
        # Loop over "movable tails" of up1, e.g. if the end of up1 is
        # [7D 5C 4C] then this loop will test [4C], then test [5C 4C], then see
        # that [7D 5C 4C] is not a valid move. We can always go through this
        # loop at least once.
        if len(up1) == 0:
            # no cards to move
            return False
        if len(up2) == 0:
            # dest column is empty; can move the biggest (and only the biggest) movable tail
            cardsToMove = self.find_tail(up1)
            # cardsToMove is always at least 1
            if doMove:
                up2.extend(up1[-cardsToMove:])
                up1[-cardsToMove:] = []
            return True
        #
        cardsToMove = 1
        while True:
            # If the numeric value of the card "cardsToMove" from the top in col1 is
            # one less than the numeric value of the topmost card in col2, then
            # the move is legal.
            if self._up[col1][-cardsToMove][0] == (self._up[col2][-1][0] - 1):
                # Can move it!
                if doMove:
                    self._up[col2].extend(self._up[col1][-cardsToMove:])
                    self._up[col1][-cardsToMove:] = []
                    # see if we need to flip a _down card
                    if len(self._up[col1]) == 0:
                        if len(self._down[col1]) > 0:
                            self._up[col1].append(self._down[col1][0])
                            self._down[col1][0:1] = []
                    # see if we finished a stack
                    if self.find_tail(up2) == 13:
                        if verbosity >= 1:
                            print 'Done with',
                            print up2[-13:0]
                        up2[-13:0] = []
                        self._done = self._done + 1
                        if self._done == 8:
                            print 'WINNER!'
                            print self._moves
                            pass
                return True
            cardsToMove = cardsToMove + 1
            if cardsToMove > len(self._up[col1]):
                # tried all tails of col1, none are a legal move
                return False
            card1 = self._up[col1][-cardsToMove]  # one deeper in stack
            card2 = self._up[col1][-cardsToMove + 1]  # card on top of it
            # deeper card must be one less, and must be same suit
            if (card1[0] != (card2[0] + 1)) or (card1[1] != card2[1]):
                # next tail is not a valid move
                return False

    def play(self):
        self.invariant()
        self._nest = self._nest + 1
        if verbosity >= 1:
            print self._nest,
        while True:
            for c1 in range(10):
                for c2 in range(10):
                    if c1 == c2:
                        continue
                    if self.move(c1, c2, False):
                        if verbosity >= 2:
                            print 'Can move from', c1, 'to', c2
                        # play one game where we move, and one where we don't
                        new_self = copy.deepcopy(self)
                        new_self.move(c1, c2, True)
                        new_self._moves.append((c1, c2))
                        # Now self is the game without the move, and new_self is
                        # the game with the move. The self game will continue with
                        # this loop, and we interject the new_self here.
                        # print 'Old:'
                        # self.print_table()
                        # only play new_self if we have not already found and played it
                        h = new_self.get_hash()
                        if not h in Spider4._seen:
                            Spider4._seen.append(h)
                            if verbosity >= 2:
                                print 'New:'
                                new_self.print_table()
                            new_self.play()
                        else:
                            if verbosity >= 2:
                                print 'Seen it...'
            # out of moves; deal
            if not self.deal_one():
                # no cards in pile; we lose
                break
            if verbosity >= 2:
                print 'Deal:'
                self.print_table()
        print 'lost after', len(self._moves), 'moves'
        self._nest = self._nest - 1
        if verbosity >= 1:
            print self._nest



random.seed(0)
s = Spider4()
s.print_table()
print s.get_hash()
s.play()
pass
