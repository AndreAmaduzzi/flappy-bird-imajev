"""Every question sent to imajev, in one place, so scripts/eval_perception.py scores exactly what the agents ask.

Each entry is a TypeSafe Jev question object. `LABELS` says which frame-bank label scores it and how each answer
option maps onto that label.
"""
from __future__ import annotations

GAME_STATE = ("Flappy Bird. The yellow bird flies to the right through gaps between green pipes. "
              "Flapping makes the bird jump up; otherwise it keeps falling. Touching a pipe or the ground ends the game.")

# ------------------------------------------------------------------------------------------- direct
DIRECT_QUESTION = "Should the bird flap now to pass through the next gap?"

DIRECT = {
    # The question exactly as the demo states it, bare options.
    "plain": {"type": "choice", "instructions": DIRECT_QUESTION, "criteria": {"flap": None, "wait": None}},
    # Same question, options described.
    "described": {"type": "choice", "instructions": DIRECT_QUESTION, "criteria": {
        "flap": "the bird is too low for the next gap, or falling toward the lower pipe or the ground",
        "wait": "the bird is level with or above the next gap and can fall into it"}},
}

DIRECT_TWO_FRAMES = ("The first image is the previous game frame and the second image is the current frame. "
                     + DIRECT_QUESTION)

# ------------------------------------------------------------------------------------------- perception
PERCEPTION = {
    "vs_gap_plain": {"type": "choice", "instructions":
                     "Where is the yellow bird vertically compared to the opening between the next pair of green pipes?",
                     "criteria": {"above": None, "inside": None, "below": None}},
    "vs_gap_described": {"type": "choice", "instructions":
                         "Where is the yellow bird vertically compared to the opening between the next pair of green pipes?",
                         "criteria": {"above": "higher than the bottom end of the upper pipe",
                                      "inside": "between the bottom end of the upper pipe and the top end of the lower pipe",
                                      "below": "lower than the top end of the lower pipe"}},
    "vs_center": {"type": "choice", "instructions":
                  "Is the yellow bird higher or lower than the middle of the opening between the next pair of green pipes?",
                  "criteria": {"higher": None, "lower": None}},
    "below_gap": {"type": "noul", "instructions":
                  "The yellow bird is lower than the top end of the next lower green pipe."},
    "above_gap": {"type": "noul", "instructions":
                  "The yellow bird is higher than the bottom end of the next upper green pipe."},
    "near_ground": {"type": "noul", "instructions": "The yellow bird is close to the ground at the bottom."},
    "hit_lower": {"type": "noul", "instructions": "The yellow bird is about to hit the lower green pipe in front of it."},
    "high_in_gap": {"type": "noul", "instructions":
                    "The yellow bird is in the upper part of the opening between the next green pipes, or above it."},
    "low_in_gap": {"type": "noul", "instructions":
                   "The yellow bird is in the lower part of the opening between the next green pipes, or below it."},
    "pipe_close": {"type": "noul", "instructions": "The next green pipe is close to the yellow bird horizontally."},
    "falling": {"type": "noul", "instructions": "The yellow bird is tilted nose-down, as when it is falling."},
}

# question id -> (frame-bank label, {answer option: label value})
LABELS = {
    "plain": ("oracle", {"flap": "flap", "wait": "wait"}),
    "described": ("oracle", {"flap": "flap", "wait": "wait"}),
    "two_frames": ("oracle", {"flap": "flap", "wait": "wait"}),
    "vs_gap_plain": ("vs_gap", {"above": "above", "inside": "inside", "below": "below"}),
    "vs_gap_described": ("vs_gap", {"above": "above", "inside": "inside", "below": "below"}),
    "vs_center": ("vs_center", {"higher": "higher", "lower": "lower"}),
    "below_gap": ("vs_gap_below", {"yes": True, "no": False}),
    "above_gap": ("vs_gap_above", {"yes": True, "no": False}),
    "near_ground": ("near_ground", {"yes": True, "no": False}),
    "hit_lower": ("near_lower_pipe", {"yes": True, "no": False}),
    "low_in_gap": ("near_lower_pipe", {"yes": True, "no": False}),
    "high_in_gap": ("near_upper_pipe", {"yes": True, "no": False}),
    "pipe_close": ("pipe_close", {"yes": True, "no": False}),
    "falling": ("falling", {"yes": True, "no": False}),
}
