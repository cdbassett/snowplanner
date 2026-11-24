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
        self.fixed = False # fixed rectangles (e.g. gates) are never moved by overlap correction

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
        self.fixed = self.fixed or other.fixed
        return self

    def as_tuple(self):
        return (self.left, self.top, self.width, self.height)

    def __str__(self):
        return "Rect" + str(self.as_tuple())

    @staticmethod
    def has_overlaps(rectangles):
        for (r1, r2) in itertools.combinations(rectangles, 2):
            if not (r1.fixed and r2.fixed) and r1.overlap(r2):
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

        # identical centers give no direction, so break the tie by index (keeps one of them from staying stuck on a fixed rect)
        overlap_vectors = [(rect.center_vec(r) if any(rect.center_vec(r)) else ((0, 1) if idx < i else (0, -1))) for i, r in enumerate(self.rectangles)
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
            if r.fixed:
                continue
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


def push_off_fixed(rectangles, max_x=None, max_y=None):
    """Neighbors can squeeze a rect back onto a fixed one and stall the stepper, so finish by moving the
    rect out of any fixed rect along the shortest way, accepting small overlaps with other movable rects."""
    fixed = [r for r in rectangles if r.fixed]

    for rect in rectangles:
        if rect.fixed:
            continue

        for _ in range(len(fixed) + 1): # moving out of one fixed rect may land in another
            hit = next((f for f in fixed if rect.overlap(f)), None)

            if hit is None:
                break

            options = [(hit.right - rect.left, hit.right - rect.left, 0), (rect.right - hit.left, hit.left - rect.right, 0),
                    (hit.bottom - rect.top, 0, hit.bottom - rect.top), (rect.bottom - hit.top, 0, hit.top - rect.bottom)]

            if max_x is not None: # skip directions that leave the bounds
                options = [o for o in options if 0 <= rect.left + o[1] and rect.right + o[1] <= max_x and 0 <= rect.top + o[2] and rect.bottom + o[2] <= max_y] or options

            _, dx, dy = min(options)
            rect.left += dx
            rect.top += dy


def overlapping_pairs(rectangles):
    """Index pairs of overlapping rectangles (two fixed ones are left out), found by sweeping over the left edges instead of testing every pair"""
    order = sorted(range(len(rectangles)), key=lambda i: rectangles[i].left)
    pairs = []

    for pos, i in enumerate(order):
        a = rectangles[i]
        right = a.right

        for j in order[pos + 1:]:
            b = rectangles[j]

            if b.left >= right:
                break

            if not (a.fixed and b.fixed) and a.top < b.bottom and b.top < a.bottom:
                pairs.append((i, j))

    return pairs


def separation_step(rectangles, pairs, max_x=None, max_y=None):
    """Moves every rectangle out of the ones it overlaps, along the way that needs the least movement and by the amount it overlaps (half each between two movable ones, all of it for the one that is not fixed). Returns whether anything moved."""
    push = {}  # index -> [left, right, up, down] largest push in each direction

    def add(i, direction, amount):
        if not rectangles[i].fixed:
            slot = push.setdefault(i, [0, 0, 0, 0])
            slot[direction] = max(slot[direction], amount)

    for i, j in pairs:
        a, b = rectangles[i], rectangles[j]
        ox, oy = a.overlapx(b), a.overlapy(b)
        amount = ox if ox <= oy else oy
        share_a = amount if b.fixed else (amount + 1) // 2
        share_b = amount if a.fixed else amount // 2 + (amount % 2 if b.fixed else 0)

        if ox <= oy:
            a_is_left = a.midx < b.midx or (a.midx == b.midx and i < j) # identical centers: break the tie by index
            add(i, 0 if a_is_left else 1, share_a)
            add(j, 1 if a_is_left else 0, share_b)
        else:
            a_is_up = a.midy < b.midy or (a.midy == b.midy and i < j)
            add(i, 2 if a_is_up else 3, share_a)
            add(j, 3 if a_is_up else 2, share_b)

    moved = False
    helper = BaseStrategy(rectangles, max_x, max_y)

    for i, (left, right, up, down) in push.items():
        rect = rectangles[i]
        before = (rect.left, rect.top)
        rect.left += right - left
        rect.top += down - up
        helper.correct_rect_bounds(rect)
        moved = moved or (rect.left, rect.top) != before

    return moved


def unit_step(rectangles, pairs, max_x=None, max_y=None):
    """Moves each rectangle one pixel away from the center of the ones it overlaps (finer than separation_step, which can swing back and forth between neighbours)"""
    vecs = {}

    for i, j in pairs:
        a, b = rectangles[i], rectangles[j]
        v = a.center_vec(b) if any(a.center_vec(b)) else ((0, 1) if i < j else (0, -1))
        va = vecs.setdefault(i, [0, 0])
        va[0] += v[0]
        va[1] += v[1]
        vb = vecs.setdefault(j, [0, 0])
        vb[0] -= v[0]
        vb[1] -= v[1]

    helper = BaseStrategy(rectangles, max_x, max_y)

    for i, (vx, vy) in vecs.items():
        rect = rectangles[i]

        if rect.fixed:
            continue

        mag = math.hypot(vx, vy)

        if mag:
            rect.left += round(vx / mag)
            rect.top += round(vy / mag)
            helper.correct_rect_bounds(rect)


def correct_rect_overlaps(rectangles, max_x=None, max_y=None, max_tries = 300, patience = 8):
    best = None
    stale = 0

    for t in range(max_tries):  # big steps first
        pairs = overlapping_pairs(rectangles)

        if not pairs:
            break

        if best is None or len(pairs) < best:
            best, stale = len(pairs), 0
        else:
            stale += 1

            if stale >= patience: # the big steps are swinging back and forth: finish with one pixel steps
                break

        if not separation_step(rectangles, pairs, max_x, max_y):
            break

    for t in range(max_tries):
        pairs = overlapping_pairs(rectangles)

        if not pairs:
            break

        unit_step(rectangles, pairs, max_x, max_y)

    push_off_fixed(rectangles, max_x, max_y)


# Cache of finished corrections, keyed by geometry only so that highlight/filter changes which leave
# the rectangles identical (or remove some of them) don't redo the expensive correction.
_layout_cache = {}  # (max_x, max_y, group flag) -> list of {original rect tuple: (deltax, deltay)}, most recent last
_LAYOUTS_PER_BOUNDS = 32

def _rect_key(rect):
    return (rect.original_left, rect.original_top, rect.width, rect.height, rect.fixed)

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
