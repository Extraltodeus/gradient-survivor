"""Global constants, tuning knobs and the UI palette."""

TITLE     = "GRADIENT DESCENT"
SUBTITLE  = "an AI survivor"
VERSION   = "1.0"

W, H      = 1280, 720
CX, CY    = W // 2, H // 2
FPS       = 60

# ---- fonts -------------------------------------------------------------
FONT_MONO = "consolas,cascadiamonoregular,couriernew"

# ---- UI palette --------------------------------------------------------
INK       = (232, 240, 255)
INK_DIM   = (140, 158, 186)
INK_FAINT = (78, 92, 116)
PANEL     = (13, 17, 26)
PANEL_HI  = (22, 28, 42)
LINE      = (44, 56, 80)

CYAN      = (93, 240, 255)
BLUE      = (63, 169, 245)
VIOLET    = (180, 92, 255)
MAGENTA   = (255, 78, 205)
RED       = (255, 68, 92)
ORANGE    = (255, 148, 46)
YELLOW    = (255, 224, 92)
GREEN     = (60, 255, 158)
WHITE     = (255, 255, 255)
GOLD      = (255, 205, 90)

XP_COL    = (110, 210, 255)
HP_COL    = (80, 240, 170)

RARITY_COL = {0: INK_DIM, 1: (120, 200, 255), 2: (190, 130, 255), 3: (255, 190, 80)}

# ---- player ------------------------------------------------------------
P_RADIUS      = 11
P_SPEED       = 232.0
P_HP          = 100.0
P_IFRAMES     = 0.55
P_MAGNET      = 155.0
P_PICKUP      = 24.0

# ---- world / caps ------------------------------------------------------
CELL          = 88          # spatial hash cell size
MAX_ENEMIES   = 520
MAX_PROJ      = 760
MAX_PARTS     = 620
DESPAWN_DIST  = 1150.0      # enemies further than this from the player recycle

# ---- progression -------------------------------------------------------
RUN_LENGTH    = 20 * 60     # seconds until the final boss window
MAX_PROCESSES = 6
MAX_TRAIT_RK  = 5

def xp_for_level(n):
	# gentle early, steeper later; keeps the level-up drumbeat frequent but slowing
	return int(4 + n * 3.4 + (n ** 1.62) * 0.9)
