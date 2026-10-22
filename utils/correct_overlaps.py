import itertools
import math
import sys
import random

from icecream import ic

# code taken and modified from
# https://github.com/mwkling/rectangle-overlap

class Rectangle:
    def __init__(self, left, top, width, height):
        self.left   = int(left)
        self.top    = int(top)
        self.width  = int(width)
        self.height = int(height)

        # So we can track how far the rectangle moved from original position
        self.original_left = self.left
        self.original_top  = self.top

    @property
    def right(self):
        return self.left + self.width

    @property
    def bottom(self):
        return self.top + self.height

    @property
    def area(self):
        return self.width * self.height

    @property
    def original_right(self):
        return self.original_left + self.width

    @property
    def original_bottom(self):
        return self.original_top + self.height

    @property
    def midx(self):
        return (self.left + self.right) // 2

    @property
    def midy(self):
        return (self.top + self.bottom) // 2

    @property
    def original_midx(self):
        return (self.original_left + self.original_right) // 2

    @property
    def original_midy(self):
        return (self.original_top + self.original_bottom) // 2

    @property
    def distance_from_original(self):
        return math.sqrt((self.left - self.original_left) ** 2 + (self.top - self.original_top) ** 2)

    @property
    def deltax(self):
        return self.original_left - self.left

    @property
    def deltay(self):
        return self.original_top - self.top

    def rotate(self, theta):
        # Note: important not to assign directly to self.left here first, as that would then mess
        # up calculation of the value for self.top
#        new_left = self.original_left + self.deltax * math.cos(theta) - self.deltay * math.sin(theta)
#        new_top  = self.original_top + self.deltax * math.sin(theta) + self.deltay * math.cos(theta)
        new_left = round(self.original_left + self.deltax * math.cos(theta) - self.deltay * math.sin(theta))
        new_top  = round(self.original_top + self.deltax * math.sin(theta) + self.deltay * math.cos(theta))

        self.left = new_left
        self.top  = new_top

    def overlap(self, other):
        if(self.left >= other.right or other.left >= self.right):
            return False
        if(self.top >= other.bottom or other.top >= self.bottom):
            return False
        return True

    def overlapx(self, other):
        return max(0, min(self.right, other.right) - max(self.left, other.left))

    def overlapy(self, other):
        return max(0, min(self.bottom, other.bottom) - max(self.top, other.top))

    def overlap_rect(self, other):
        left = max(self.left, other.left)
        top = max(self.top, other.top)
        return Rectangle(left, top, self.overlapx(other), self.overlapy(other))

    def center_vec(self, other):
        return (self.midx - other.midx, self.midy - other.midy)

    def combine(self, other):
        self.left = min(self.left, other.left)
        self.top = min(self.top, other.top)
        self.width = max(self.right, other.right) - self.left
        self.height = max(self.bottom, other.bottom) - self.top
        self.original_left = min(self.original_left, other.original_left)
        self.original_top = min(self.original_top, other.original_top)
        return self

    def as_tuple(self):
        return (self.left, self.top, self.width, self.height)

    def __str__(self):
        return "Rect" + str(self.as_tuple())

    @staticmethod
    def has_overlaps(rectangles):
        for (r1, r2) in itertools.combinations(rectangles, 2):
            if r1.overlap(r2):
                return True
        return False

    @staticmethod
    def overlap_rectangles(rectangles):
        return [r1.overlap_rect(r2) for r1, r2 in itertools.combinations(rectangles, 2)
                if r1.overlap(r2)]

    @staticmethod
    def total_movement(rectangles):
        return sum([r.distance_from_original for r in rectangles])

class BaseStrategy:
    def __init__(self, rectangles, max_x=None, max_y=None):
        self.rectangles = rectangles
        self.check_rectangles = rectangles[:]
        self.max_x = sys.maxsize if max_x is None else  max_x
        self.max_y = sys.maxsize if max_y is None else  max_y
        self.correct_bounds = max_x is not None
#        self.max_x = sys.maxsize if max_x is None else  max_x
#        self.max_y = sys.maxsize if max_y is None else  max_y

        if 0 and max_y is not None and max_x is not None:
            # sides
            self.check_rectangles.append(Rectangle(0, max_y, max_x, max_y))
            self.check_rectangles.append(Rectangle(0, -max_y, max_x, max_y))
            self.check_rectangles.append(Rectangle(-max_x, 0, max_x, max_y))
            self.check_rectangles.append(Rectangle(max_x, 0, max_x, max_y))
            # corners
            if 0:
                self.check_rectangles.append(Rectangle(max_x, max_y, max_x, max_y))
                self.check_rectangles.append(Rectangle(-max_x, -max_y, max_x, max_y))
                self.check_rectangles.append(Rectangle(max_x, -max_y, max_x, max_y))
                self.check_rectangles.append(Rectangle(-max_x, max_y, max_x, max_y))

    def correct_rect_bounds(self, rect):
        if self.correct_bounds:
            if rect.left < 0:
                rect.left = 0

            if rect.top < 0:
                rect.top = 0

            if rect.right > self.max_x:
                rect.left = self.max_x - rect.width

            if rect.bottom > self.max_y:
                rect.top = self.max_y - rect.height



# This strategy finds all overlaps for all rectangles, then computes a vector for each rectangle
# in the opposite direction of all it overlaps, normalizes and translates by that distance
class Separation(BaseStrategy):
    def __init__(self, rectangles, max_x=None, max_y=None):
        super().__init__(rectangles, max_x, max_y)

#            ic(len(self.rectangles), len(self.check_rectangles))
#            ic(Rectangle.has_overlaps(self.rectangles))
#            ic(Rectangle.has_overlaps(self.check_rectangles))

    def translate_vector(self, idx):
        rect = self.rectangles[idx]

        overlap_vectors = [rect.center_vec(r) for i, r in enumerate(self.rectangles)
                if i != idx and rect.overlap(r)]

        if len(overlap_vectors) == 0:
            return (0, 0)
        else:
            # This adds up vectors from each overlap if there were multiple
            return list(map(sum, zip(*overlap_vectors)))

    def normalize(self, pair):
        mag = math.sqrt(pair[0]**2 + pair[1]**2)

        if mag == 0:
            return pair
        else:
            return (pair[0] / mag, pair[1] / mag)

    def step(self):
        vecs = [self.normalize(self.translate_vector(i)) for i in range(len(self.rectangles))]

        for i, r in enumerate(self.rectangles):
#            r.left += vecs[i][0]
#            r.top += vecs[i][1]
            r.left += round(vecs[i][0])
            r.top += round(vecs[i][1])
            self.correct_rect_bounds(r)


class Annealing:
    def __init__(self, rectangles, max_x=None, max_y=None):
        super().__init__(rectangles, max_x, max_y)

        self.temperature = 1.0

        # TODO how to set/configure these parameters in a smarter way
        self.magnitude = 10
        self.rounds = 5000

    # Energy measure is the total area of overlap of this rectangle with others
    def energy(self, idx):
        rect = self.rectangles[idx]

        # TODO incorporate distance from original position?
        return sum([rect.overlapx(r) * rect.overlapy(r) for i, r in enumerate(self.check_rectangles) if i != idx and rect.overlap(r)])

    def step(self):
        if self.temperature <= 0:
            return

        for n_try in range(10000):
                # TODO make smarter random choice here in some way?
            i = random.randint(0, len(self.rectangles) - 1)
            e = self.energy(i)

            if e > 0:
                    # Now, randomly translate, but remember old position
                rect = self.rectangles[i]
                old_top = rect.top
                old_left = rect.left

                # TODO incorporate rotational moves as well?
                if random.random() > 0.5:
#                    rect.top += (random.random() * 15) * (random.random() - 0.5)
#                    rect.left += (random.random() * 15) * (random.random() - 0.5)
                    rect.top += round((random.random() * 15) * (random.random() - 0.5))
                    rect.left += round((random.random() * 15) * (random.random() - 0.5))
                else:
                    theta = random.random() * 2 * 3.1416
                    rect.rotate(theta)

                self.correct_rect_bounds(rect)
                newe = self.energy(i)

                    # Acceptance check compares new energy with previous w/temperature
                accept = False

#                if newe < e and False:
#                    accept = True
#                else:
                if 1:
                    try:
                        accept = random.random() < math.exp((e - newe) / self.temperature)
                    except OverflowError:
                        # Not accepted
                        pass

                if accept:
                    break
                else:
                    rect.top = old_top
                    rect.left = old_left

        self.temperature -= 1 / self.rounds

strategy = Separation
#strategy = Annealing


def correct_rect_overlaps(rectangles, max_x=None, max_y=None, max_tries = 1000):
    stepper = strategy(rectangles, max_x, max_y)

    for t in range(max_tries):
        if Rectangle.has_overlaps(stepper.check_rectangles):
            stepper.step()

#    ic(Rectangle.has_overlaps(stepper.rectangles))
#    ic(Rectangle.has_overlaps(stepper.check_rectangles))

#    print(Rectangle.total_movement(stepper.rectangles))


# Cache of finished corrections, keyed by geometry only so that highlight/filter changes which leave
# the rectangles identical (or remove some of them) don't redo the expensive correction.
_layout_cache = {}  # (max_x, max_y, group flag) -> list of {original rect tuple: (deltax, deltay)}, most recent last
_LAYOUTS_PER_BOUNDS = 32

def _rect_key(rect):
    return (rect.original_left, rect.original_top, rect.width, rect.height)

def _apply_delta(rect, delta):
    rect.left = rect.original_left - delta[0]
    rect.top = rect.original_top - delta[1]

def correct_rect_overlaps_cached(rectangles, max_x=None, max_y=None, group_key=None):
    """Like correct_rect_overlaps, reusing a cached layout when possible. Returns "exact", "subset" or "miss"."""
    layouts = _layout_cache.setdefault((max_x, max_y, group_key), [])
    keys = [_rect_key(r) for r in rectangles]
    key_set = set(keys)

    if len(key_set) == len(keys): # duplicate geometry can't be told apart, so don't cache those
        best = None

        for layout in layouts:
            if key_set <= layout.keys() and (best is None or len(layout) < len(best)):
                best = layout

        if best is not None:
            for rect, key in zip(rectangles, keys):
                _apply_delta(rect, best[key])

            layouts.remove(best)
            layouts.append(best) # LRU refresh
            return "exact" if len(best) == len(keys) else "subset"

    correct_rect_overlaps(rectangles, max_x, max_y)

    if len(key_set) == len(keys):
        layouts.append({key: (r.deltax, r.deltay) for r, key in zip(rectangles, keys)})
        del layouts[:-_LAYOUTS_PER_BOUNDS]

    return "miss"
