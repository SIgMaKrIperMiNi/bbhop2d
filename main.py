# -*- coding: utf-8 -*-
"""
BHOP — игра про баннихоп (bunnyhop) для Pydroid 3 / pygame.

Запуск: открой файл в Pydroid 3 -> Pip -> установи "pygame" (если ещё нет) -> ▶.
Играть лучше в альбомной ориентации.

Суть: как в Counter-Strike / Half-Life. Прыгай без остановки и в воздухе
поворачивай обзор в сторону стрейфа — так скорость растёт выше обычного
предела бега. Приземлился и сразу прыгнул — трение не успевает тебя замедлить.
"""
import math, os, sys, json, time, random, array

# ======================= ФИЗИКА (единицы как в Source) =======================
TICK = 1.0 / 120.0
GRAVITY = 800.0
JUMP_V = 290.0
MAX_GROUND = 250.0
GROUND_ACCEL = 10.0
FRICTION = 5.2
STOP_SPEED = 100.0
AIR_ACCEL = 14.0
AIR_CAP = 36.0
SPEED_SOFT = 1500.0
AIR_DRAG = 0.35           # без стрейфа в воздухе скорость плавно падает (тормоз)
JUMP_BUFFER = 0.13        # прыжок, нажатый чуть раньше приземления, засчитывается
AUTO_MIN_SPEED = 200.0    # автопрыжок включается, когда разбежался
PLAYER_R = 16.0
EDGE_ASSIST = 22.0        # небольшая "поблажка" на краю платформы
FALL_Z = -420.0
AIR_TIME = 2 * JUMP_V / GRAVITY


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


class Pad(object):
    def __init__(self, cx, cy, ang, hl, hw, kind='pad', s0=0.0):
        self.cx, self.cy, self.ang, self.hl, self.hw, self.kind = cx, cy, ang, hl, hw, kind
        self.c, self.s = math.cos(ang), math.sin(ang)
        self.rad = math.hypot(hl, hw)
        self.s0 = s0            # длина пути до начала платформы
        self.visited = False

    def contains(self, x, y, m=0.0):
        dx = x - self.cx
        dy = y - self.cy
        r = self.rad + m
        if dx * dx + dy * dy > r * r:
            return False
        lx = dx * self.c + dy * self.s
        ly = -dx * self.s + dy * self.c
        return abs(lx) <= self.hl + m and abs(ly) <= self.hw + m

    def local_x(self, x, y):
        return (x - self.cx) * self.c + (y - self.cy) * self.s + self.hl

    def corners(self):
        out = []
        for lx, ly in ((-self.hl, -self.hw), (self.hl, -self.hw), (self.hl, self.hw), (-self.hl, self.hw)):
            out.append((self.cx + lx * self.c - ly * self.s, self.cy + lx * self.s + ly * self.c))
        return out


class Level(object):
    """Трасса из платформ: P(длина, ширина[, тип]) — платформа, G(длина) — пропасть, T(градусы) — поворот."""

    def __init__(self, name, desc, cmds, medals=(0, 0, 0)):
        self.name, self.desc, self.medals = name, desc, medals
        self.pads = []
        self.endless = False
        x = y = 0.0
        a = -math.pi / 2
        s = 0.0
        for c in cmds:
            op = c[0]
            if op == 'P':
                L, Wd = c[1], c[2]
                kind = c[3] if len(c) > 3 else 'pad'
                self.pads.append(Pad(x + math.cos(a) * L / 2, y + math.sin(a) * L / 2, a, L / 2, Wd / 2, kind, s))
                x += math.cos(a) * L
                y += math.sin(a) * L
                s += L
            elif op == 'G':
                x += math.cos(a) * c[1]
                y += math.sin(a) * c[1]
                s += c[1]
            elif op == 'T':
                a += math.radians(c[1])
        p0 = self.pads[0]
        self.start = (p0.cx - p0.c * (p0.hl - 90), p0.cy - p0.s * (p0.hl - 90), p0.ang)
        self.total = s

    def pad_at(self, x, y, m=0.0):
        for p in self.pads:
            if p.contains(x, y, m):
                return p
        return None

    def update(self, px, py):
        pass


class Endless(Level):
    """Бесконечная трасса: генерируется впереди игрока, сужается и усложняется."""

    def __init__(self, seed=None):
        self.name = 'ENDLESS'
        self.desc = ''
        self.medals = (0, 0, 0)
        self.endless = True
        self.rng = random.Random(seed)
        self.pads = []
        self.x = self.y = 0.0
        self.a = -math.pi / 2
        self.s = 0.0
        self.n = 0
        self.turn_bias = 0.0
        p = Pad(0, -300, self.a, 400, 330, 'start', 0.0)
        self.pads.append(p)
        self.y = -700.0
        self.s = 800.0
        self.start = (0.0, -80.0, self.a)
        self.total = 1e9
        for _ in range(8):
            self._gen()

    def _gen(self):
        r = self.rng
        k = min(1.0, self.n / 60.0)                 # сложность 0..1
        gap = r.uniform(40, 70) + 70 * k
        L = r.uniform(330, 520)
        Wd = 520 - 270 * k + r.uniform(-30, 30)
        self.x += math.cos(self.a) * gap
        self.y += math.sin(self.a) * gap
        self.s += gap
        turn = r.uniform(-24, 24) - self.turn_bias * 0.5
        self.turn_bias = max(-60, min(60, self.turn_bias + turn))
        self.a += math.radians(turn)
        self.pads.append(Pad(self.x + math.cos(self.a) * L / 2, self.y + math.sin(self.a) * L / 2,
                             self.a, L / 2, Wd / 2, 'pad', self.s))
        self.x += math.cos(self.a) * L
        self.y += math.sin(self.a) * L
        self.s += L
        self.n += 1

    def update(self, px, py):
        last = self.pads[-1]
        while math.hypot(last.cx - px, last.cy - py) < 2600:
            self._gen()
            last = self.pads[-1]
        while len(self.pads) > 14 and math.hypot(self.pads[0].cx - px, self.pads[0].cy - py) > 2400:
            self.pads.pop(0)


class Player(object):
    def __init__(self):
        self.reset(0, 0, -math.pi / 2)

    def reset(self, x, y, yaw):
        self.x, self.y, self.yaw = x, y, yaw
        self.vx = self.vy = 0.0
        self.z = 0.0
        self.vz = 0.0
        self.ground = True
        self.buf = 0.0
        self.ground_t = 0.0
        self.ev_jump = self.ev_land = False
        self.perfect = None
        self.dead = False
        self.hops = 0

    @property
    def speed(self):
        return math.hypot(self.vx, self.vy)

    def _accel(self, wx, wy, wishspeed, accel, dt):
        cur = self.vx * wx + self.vy * wy
        add = wishspeed - cur
        if add <= 0:
            return
        a = accel * wishspeed * dt
        if a > add:
            a = add
        self.vx += a * wx
        self.vy += a * wy

    def step(self, dt, strafe, auto_jump, forward, level):
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        if self.buf > 0:
            self.buf -= dt
        want = self.buf > 0 or (auto_jump and self.speed >= AUTO_MIN_SPEED)
        if self.ground and want:
            self.vz = JUMP_V
            self.ground = False
            self.buf = 0.0
            self.ev_jump = True
            self.perfect = self.ground_t <= 0.03
        if self.ground:
            self.ground_t += dt
            sp = self.speed
            if sp > 0.01:
                drop = max(sp, STOP_SPEED) * FRICTION * dt
                ns = max(sp - drop, 0.0) / sp
                self.vx *= ns
                self.vy *= ns
            wx = (c if forward else 0.0) + strafe * (-s)
            wy = (s if forward else 0.0) + strafe * c
            ln = math.hypot(wx, wy)
            if ln > 0:
                self._accel(wx / ln, wy / ln, MAX_GROUND, GROUND_ACCEL, dt)
        elif strafe:
            self._accel(strafe * (-s), strafe * c, AIR_CAP, AIR_ACCEL, dt)
        else:
            k = max(0.0, 1.0 - AIR_DRAG * dt)
            self.vx *= k
            self.vy *= k
        sp = self.speed
        if sp > SPEED_SOFT:
            k = SPEED_SOFT / sp
            self.vx *= k
            self.vy *= k
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.ground:
            if level.pad_at(self.x, self.y, EDGE_ASSIST) is None:
                self.ground = False
                self.vz = 0.0
        else:
            self.vz -= GRAVITY * dt
            self.z += self.vz * dt
            if self.z <= 0 and self.vz < 0:
                if level.pad_at(self.x, self.y, EDGE_ASSIST) is not None:
                    self.z = 0.0
                    self.vz = 0.0
                    self.ground = True
                    self.ground_t = 0.0
                    self.ev_land = True
                    self.hops += 1
                elif self.z < FALL_Z:
                    self.dead = True


# ============================ УРОВНИ ============================
def _rep(n, cmds):
    out = []
    for _ in range(n):
        out += cmds
    return out


def build_levels():
    L = []
    # 1 — широкая и добрая
    c = [('P', 700, 700, 'start')]
    c += _rep(5, [('G', 70), ('P', 460, 640)])
    c += [('T', -30)] + _rep(5, [('G', 80), ('P', 440, 600)])
    c += [('G', 80), ('P', 440, 600, 'cp')]
    c += [('T', 60)] + _rep(6, [('G', 80), ('P', 440, 580)])
    c += [('T', -30)] + _rep(4, [('G', 90), ('P', 440, 560)])
    c += [('T', -30)] + _rep(4, [('G', 90), ('P', 440, 560)])
    c += [('G', 90), ('P', 800, 700, 'finish')]
    L.append(Level('1. РАЗМИНКА', 'Широкая трасса. Учись раскачивать скорость.', c))
    # 2 — змейка
    c = [('P', 600, 600, 'start')]
    for i in range(7):
        sgn = 1 if i % 2 == 0 else -1
        c += [('T', 26 * sgn), ('G', 90), ('P', 420, 480), ('G', 90), ('P', 420, 480), ('T', -26 * sgn)]
        c += [('G', 90), ('P', 420, 500, 'cp' if i == 3 else 'pad')]
    c += [('G', 90), ('P', 800, 640, 'finish')]
    L.append(Level('2. ЗМЕЙКА', 'Плавные виражи туда-сюда.', c))
    # 3 — длинные прямые с провалами
    c = [('P', 600, 520, 'start')]
    c += _rep(8, [('G', 90), ('P', 500, 440)])
    c += [('G', 95), ('P', 500, 440, 'cp')]
    c += _rep(8, [('G', 100), ('P', 520, 420)])
    c += [('T', 25)] + _rep(2, [('G', 100), ('P', 500, 420)])
    c += [('G', 100), ('P', 500, 420, 'cp')] + _rep(2, [('G', 100), ('P', 500, 420)])
    c += [('T', -25)] + _rep(3, [('G', 100), ('P', 500, 420)])
    c += [('T', -22)] + _rep(3, [('G', 100), ('P', 500, 420)])
    c += [('G', 110), ('P', 800, 600, 'finish')]
    L.append(Level('3. ПРОВАЛЫ', 'Между платформами пропасти. Нужна скорость.', c))
    # 4 — спираль
    c = [('P', 600, 520, 'start')]
    for i in range(22):
        c += [('T', 12), ('G', 80), ('P', 380, 400 - min(i, 6) * 10, 'cp' if i == 10 else 'pad')]
    c += [('G', 90), ('P', 800, 600, 'finish')]
    L.append(Level('4. СПИРАЛЬ', 'Длинный вираж по кругу — поворачивай в одну сторону.', c))
    # 5 — узкая тропа
    c = [('P', 600, 500, 'start')]
    for i in range(15):
        sgn = 1 if (i // 2) % 2 == 0 else -1
        c += [('T', 20 * sgn), ('G', 100), ('P', 400, 260, 'cp' if i == 7 else 'pad')]
    c += [('G', 110), ('P', 800, 520, 'finish')]
    L.append(Level('5. УЗКАЯ ТРОПА', 'Тонкая дорожка. Точность важнее скорости.', c))
    # 6 — финал
    c = [('P', 600, 460, 'start')]
    for i in range(20):
        sgn = 1 if i % 3 != 2 else -1
        c += [('T', 26 * sgn), ('G', 120 + 4 * i), ('P', 420, 300 - min(i, 12) * 6, 'cp' if i in (6, 13) else 'pad')]
    c += [('G', 160), ('P', 800, 520, 'finish')]
    L.append(Level('6. ГАУНТЛЕТ', 'Всё сразу. Удачи.', c))
    return L


LEVELS = build_levels()


# ============================ ИНТЕРФЕЙС (pygame) ============================
MEDALS = [(38, 60, 90), (31, 48, 72), (50, 75, 115), (31, 48, 72), (25, 39, 60), (34, 53, 80)]
for _lv, _m in zip(LEVELS, MEDALS):
    _lv.medals = _m
FALL_PENALTY = 2.0
ASSIST_RATE = 12.0   # как быстро помощник доворачивает взгляд (1/с)

# режимы управления: (авто-прыжок, авто-стрейф)
PRESETS = [(True, True), (False, True), (True, False), (False, False)]

TR = {
    'ru': {
        'sub': 'симулятор баннихопа', 'campaign': 'Кампания', 'endless': 'Бесконечный бег', 'help': 'Как играть',
        'settings': 'Настройки', 'quit': 'Выход', 'back': 'Назад', 'levels': 'Выбери уровень',
        'p0': 'Лёгкий: авто-прыжок + авто-стрейф', 'p1': 'Тайминг: свой прыжок + авто-стрейф',
        'p2': 'Стрейф: авто-прыжок + свои кнопки', 'p3': 'Про: всё вручную',
        'ctrl': 'Управление', 'sens': 'Чувствительность', 'cam': 'Камера', 'cam0': 'от первого лица', 'cam1': 'сверху (север вверху)',
        'snd': 'Звук', 'on': 'вкл', 'off': 'выкл', 'resume': 'Продолжить', 'restart': 'Заново', 'menu': 'В меню',
        'next': 'Дальше', 'time': 'Время', 'best': 'Рекорд', 'falls': 'Падений', 'speed': 'скорость', 'maxspeed': 'макс. скорость',
        'gold': 'ЗОЛОТО', 'silver': 'СЕРЕБРО', 'bronze': 'БРОНЗА', 'finish': 'ФИНИШ', 'checkpoint': 'Чекпоинт!',
        'fall': 'Падение  +%d с', 'go': 'ПОЕХАЛИ!', 'over': 'Конец забега', 'dist': 'Дистанция', 'again': 'Ещё раз',
        'perfect': 'ИДЕАЛЬНО!', 'late': 'поздно', 'jump': 'ПРЫЖОК', 'paused': 'Пауза', 'new': 'НОВЫЙ РЕКОРД!',
        'h0': 'Свайпай пальцем по экрану влево-вправо — обзор поворачивается.',
        'h1': 'В воздухе поворачивай плавно в одну сторону, потом в другую: скорость растёт выше обычного бега.',
        'h2': 'Синяя линия — куда ты реально летишь. Держи её рядом с направлением взгляда (вверх).',
        'h3': 'Приземлился — сразу прыгай. Любая задержка на земле = трение и потеря скорости.',
        'h4': 'Не падай с платформ. Жёлтые — чекпоинты. Каждое падение: +2 секунды.',
        'h5': 'В режиме «Тайминг» жми ПРЫЖОК чуть раньше касания земли. Клавиатура: стрелки — поворот, A/D — стрейф, Пробел — прыжок.',
        'hint1': 'Свайпай влево-вправо, чередуя направления',
    },
    'en': {
        'sub': 'bunnyhop simulator', 'campaign': 'Campaign', 'endless': 'Endless run', 'help': 'How to play',
        'settings': 'Settings', 'quit': 'Quit', 'back': 'Back', 'levels': 'Choose a level',
        'p0': 'Easy: auto-jump + auto-strafe', 'p1': 'Timing: manual jump + auto-strafe',
        'p2': 'Strafe: auto-jump + strafe buttons', 'p3': 'Pro: everything manual',
        'ctrl': 'Controls', 'sens': 'Sensitivity', 'cam': 'Camera', 'cam0': 'first person', 'cam1': 'top-down (north up)',
        'snd': 'Sound', 'on': 'on', 'off': 'off', 'resume': 'Resume', 'restart': 'Restart', 'menu': 'Menu',
        'next': 'Next', 'time': 'Time', 'best': 'Best', 'falls': 'Falls', 'speed': 'speed', 'maxspeed': 'top speed',
        'gold': 'GOLD', 'silver': 'SILVER', 'bronze': 'BRONZE', 'finish': 'FINISH', 'checkpoint': 'Checkpoint!',
        'fall': 'Fell  +%d s', 'go': 'GO!', 'over': 'Run over', 'dist': 'Distance', 'again': 'Again',
        'perfect': 'PERFECT!', 'late': 'late', 'jump': 'JUMP', 'paused': 'Paused', 'new': 'NEW RECORD!',
        'h0': 'Swipe left/right on the screen to turn the view.',
        'h1': 'In the air turn smoothly one way, then the other: speed grows beyond normal running.',
        'h2': 'The blue line is where you really fly. Keep it near the view direction (up).',
        'h3': 'Land and jump at once. Any delay on the ground = friction = lost speed.',
        'h4': "Don't fall off the platforms. Yellow = checkpoints. Each fall: +2 seconds.",
        'h5': 'In "Timing" mode tap JUMP just before touching the ground. Keyboard: arrows turn, A/D strafe, Space jump.',
        'hint1': 'Swipe left and right, alternating directions',
    },
}

FONT_REG = ['/system/fonts/Roboto-Regular.ttf', '/system/fonts/DroidSans.ttf', '/system/fonts/NotoSans-Regular.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            'C:/Windows/Fonts/arial.ttf', '/Library/Fonts/Arial.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf']
FONT_BOLD = ['/system/fonts/Roboto-Bold.ttf', '/system/fonts/DroidSans-Bold.ttf', '/system/fonts/NotoSans-Bold.ttf',
             '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
             'C:/Windows/Fonts/arialbd.ttf', '/Library/Fonts/Arial Bold.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf']


def speed_color(v):
    import colorsys
    t = max(0.0, min(1.0, (v - 220.0) / 700.0))
    r, g, b = colorsys.hsv_to_rgb(0.58 - 0.58 * t, 0.75, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))


def save_path():
    # Android: сохраняем рекорды и настройки в приватную папку приложения.
    # На компьютере оставляем файл рядом с main.py.
    try:
        from android.storage import app_storage_path
        base = app_storage_path()
    except Exception:
        try:
            base = os.path.dirname(os.path.abspath(__file__))
        except NameError:
            base = os.getcwd()
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return os.path.join(base, 'bhop_save.json')


def load_save():
    d = {'best': {}, 'endless': 0, 'preset': 0, 'sens': 1.0, 'cam': 0, 'sound': 1}
    try:
        with open(save_path(), 'r') as f:
            j = json.load(f)
        for k in d:
            if k in j:
                d[k] = j[k]
    except Exception:
        pass
    return d


def write_save(d):
    try:
        with open(save_path(), 'w') as f:
            json.dump(d, f)
    except Exception:
        pass


class App(object):
    def __init__(self, pg):
        self.pg = pg
        pg.init()
        win = os.environ.get('BHOP_WINDOW')
        try:
            if win:
                self.disp = pg.display.set_mode((1100, 620))
            else:
                self.disp = pg.display.set_mode((0, 0), pg.FULLSCREEN)
        except Exception:
            self.disp = pg.display.set_mode((1100, 620))
        pg.display.set_caption('BHOP')
        dw, dh = self.disp.get_size()
        self.dw, self.dh = dw, dh
        k = min(1.0, 1100.0 / max(dw, dh))
        self.W, self.H = max(320, int(dw * k)), max(200, int(dh * k))
        self.scale_needed = (self.W, self.H) != (dw, dh)
        self.scr = pg.Surface((self.W, self.H)) if self.scale_needed else self.disp
        self.u = min(self.W, self.H) / 540.0
        self.clock = pg.time.Clock()
        # шрифты
        self.fpath = next((p for p in FONT_REG if os.path.exists(p)), None) or pg.font.match_font('roboto,droidsans,notosans,dejavusans,arial')
        self.fbold = next((p for p in FONT_BOLD if os.path.exists(p)), None) or self.fpath
        self.fonts = {}
        self.lang = 'ru'
        try:
            tf = pg.font.Font(self.fpath, 20)
            m = tf.metrics(u'Ж')
            if not m or m[0] is None:
                self.lang = 'en'
        except Exception:
            self.lang = 'en'
        self.tc = {}
        self.sv = load_save()
        self.snd = {}
        self.init_sound()
        self.state = 'title'
        self.btns = []
        self.touches = {}
        self.seen_finger = False
        self.keys = set()
        self.level = None
        self.pl = Player()
        self.build_ui()
        self.rng = random.Random()
        self.parts = []
        self.trail = []
        self.toast = ('', 0.0, (255, 255, 255))
        self.cam_scale = 1.0
        self.shake = 0.0
        self.card_cache = {}

    # ---------------- вспомогательное ----------------
    def t(self, key):
        return TR[self.lang].get(key, TR['en'].get(key, key))

    def font(self, size, bold=True):
        k = (int(size), bold)
        f = self.fonts.get(k)
        if f is None:
            try:
                f = self.pg.font.Font(self.fbold if bold else self.fpath, int(size))
            except Exception:
                f = self.pg.font.Font(None, int(size * 1.2))
            self.fonts[k] = f
        return f

    def text(self, s, size, col, x, y, anchor='c', bold=True):
        f = self.font(size * self.u, bold)
        key = (s, id(f), col)
        surf = self.tc.get(key)
        if surf is None:
            if len(self.tc) > 500:
                self.tc.clear()
            surf = f.render(s, True, col)
            self.tc[key] = surf
        w, h = surf.get_size()
        if anchor == 'c':
            pos = (x - w // 2, y - h // 2)
        elif anchor == 'l':
            pos = (x, y - h // 2)
        else:
            pos = (x - w, y - h // 2)
        self.scr.blit(surf, pos)
        return w, h

    def wrap(self, s, size, maxw):
        f = self.font(size * self.u, False)
        out, cur = [], ''
        for w in s.split(' '):
            tst = (cur + ' ' + w).strip()
            if f.size(tst)[0] <= maxw or not cur:
                cur = tst
            else:
                out.append(cur)
                cur = w
        if cur:
            out.append(cur)
        return out

    def rrect(self, col, rect, rad=12, width=0):
        rect = tuple(int(v) for v in rect)
        try:
            self.pg.draw.rect(self.scr, col, rect, width, border_radius=int(rad * self.u))
        except TypeError:
            self.pg.draw.rect(self.scr, col, rect, width)

    def alpha_box(self, w, h, col, alpha, rad):
        key = (int(w), int(h), col, alpha, rad)
        s = self.card_cache.get(key)
        if s is None:
            s = self.pg.Surface((int(w), int(h)), self.pg.SRCALPHA)
            try:
                self.pg.draw.rect(s, col + (alpha,), (0, 0, int(w), int(h)), 0, border_radius=int(rad * self.u))
            except TypeError:
                self.pg.draw.rect(s, col + (alpha,), (0, 0, int(w), int(h)))
            self.card_cache[key] = s
        return s

    def init_sound(self):
        pg = self.pg
        self.snd_ok = False
        try:
            if not pg.mixer.get_init():
                pg.mixer.init(22050, -16, 1, 512)
            self.snd_ok = True
        except Exception:
            return

        def mk(segs, vol=0.25):
            rate = 22050
            buf = array.array('h')
            for f0, f1, ms in segs:
                n = int(rate * ms / 1000.0)
                ph = 0.0
                for i in range(n):
                    f = f0 + (f1 - f0) * i / max(1, n - 1)
                    ph += 2 * math.pi * f / rate
                    env = min(1.0, i / 120.0) * (1.0 - i / float(n)) ** 1.5
                    buf.append(int(math.sin(ph) * env * vol * 32767))
            try:
                return pg.mixer.Sound(buffer=buf.tobytes())
            except Exception:
                return None
        self.snd = {
            'jump': mk([(380, 520, 45)], 0.18), 'land': mk([(190, 120, 55)], 0.25),
            'cp': mk([(660, 660, 90), (880, 880, 140)], 0.25), 'ui': mk([(520, 520, 35)], 0.2),
            'fin': mk([(523, 523, 110), (659, 659, 110), (784, 784, 110), (1047, 1047, 260)], 0.25),
            'fall': mk([(420, 90, 420)], 0.25), 'tick': mk([(600, 600, 60)], 0.2), 'go': mk([(900, 900, 220)], 0.25),
            'perfect': mk([(900, 1200, 60)], 0.15),
        }

    def play(self, name):
        if self.sv['sound'] and self.snd_ok:
            s = self.snd.get(name)
            if s:
                try:
                    s.play()
                except Exception:
                    pass

    def save(self):
        write_save(self.sv)

    # ---------------- кнопки / экраны ----------------
    def mkbtn(self, label, rect, fn, style=0, sub=None, size=26):
        return {'label': label, 'rect': rect, 'fn': fn, 'style': style, 'sub': sub, 'size': size}

    def go(self, state):
        self.state = state
        self.touches = {}
        self.build_ui()

    def build_ui(self):
        W, H, u = self.W, self.H, self.u
        t = self.t
        b = []
        bw, bh = 360 * u, 62 * u
        cx = W / 2
        if self.state == 'title':
            y = H * 0.36
            items = [(t('campaign'), lambda: self.go('levels')), (t('endless'), self.start_endless),
                     (t('settings'), lambda: self.go('settings')), (t('help'), lambda: self.go('help'))]
            for i, (lab, fn) in enumerate(items):
                b.append(self.mkbtn(lab, (cx - bw / 2, y + i * 76 * u, bw, bh), fn, 0 if i < 2 else 1))
            b.append(self.mkbtn(t('quit'), (W - 130 * u, 14 * u, 112 * u, 46 * u), self.quit, 1, size=20))
        elif self.state == 'levels':
            cw, ch = 330 * u, 96 * u
            gx = 24 * u
            ncol = 2 if W >= 720 * u else 1
            x0 = cx - (ncol * cw + (ncol - 1) * gx) / 2
            for i, lv in enumerate(LEVELS):
                col, row = i % ncol, i // ncol
                r = (x0 + col * (cw + gx), H * 0.18 + row * (ch + 14 * u), cw, ch)
                b.append(self.mkbtn(lv.name, r, (lambda i=i: self.start_level(i)), 2, sub=lv.desc, size=22))
            b.append(self.mkbtn(t('back'), (18 * u, H - 70 * u, 150 * u, 52 * u), lambda: self.go('title'), 1, size=22))
        elif self.state == 'help':
            b.append(self.mkbtn(t('back'), (cx - 100 * u, H - 78 * u, 200 * u, 56 * u), lambda: self.go('title'), 1))
        elif self.state == 'settings':
            y = H * 0.18
            for i in range(4):
                b.append(self.mkbtn(t('p%d' % i), (cx - 300 * u, y + i * 66 * u, 600 * u, 56 * u),
                                    (lambda i=i: self.set_preset(i)), 3 if self.sv['preset'] == i else 2, size=21))
            y2 = y + 4 * 66 * u + 14 * u
            b.append(self.mkbtn('-', (cx + 60 * u, y2, 56 * u, 50 * u), lambda: self.chg_sens(-0.15), 1))
            b.append(self.mkbtn('+', (cx + 234 * u, y2, 56 * u, 50 * u), lambda: self.chg_sens(0.15), 1))
            b.append(self.mkbtn(t('cam0') if self.sv['cam'] == 0 else t('cam1'), (cx - 300 * u, y2 + 62 * u, 420 * u, 50 * u),
                                self.tog_cam, 1, size=20))
            b.append(self.mkbtn(t('snd') + ': ' + (t('on') if self.sv['sound'] else t('off')),
                                (cx + 134 * u, y2 + 62 * u, 166 * u, 50 * u), self.tog_snd, 1, size=20))
            b.append(self.mkbtn(t('back'), (18 * u, H - 70 * u, 150 * u, 52 * u), lambda: self.go('title'), 1, size=22))
        elif self.state == 'pause':
            for i, (lab, fn) in enumerate([(t('resume'), self.resume), (t('restart'), self.restart), (t('menu'), self.to_menu)]):
                b.append(self.mkbtn(lab, (cx - bw / 2, H * 0.34 + i * 76 * u, bw, bh), fn, 0 if i == 0 else 1))
        elif self.state in ('done', 'over'):
            y = H * 0.70
            labs = []
            if self.state == 'done' and not self.level.endless and self.lvl_idx + 1 < len(LEVELS):
                labs.append((t('next'), lambda: self.start_level(self.lvl_idx + 1)))
            labs.append((t('again') if self.level.endless else t('restart'), self.restart))
            labs.append((t('menu'), self.to_menu))
            n = len(labs)
            w = 220 * u
            for i, (lab, fn) in enumerate(labs):
                b.append(self.mkbtn(lab, (cx - (n * w + (n - 1) * 14 * u) / 2 + i * (w + 14 * u), y, w, 58 * u), fn, 0 if i == 0 else 1, size=24))
        self.btns = b

    def quit(self):
        self.running = False

    def set_preset(self, i):
        self.sv['preset'] = i
        self.save()
        self.play('ui')
        self.build_ui()

    def chg_sens(self, d):
        self.sv['sens'] = round(max(0.4, min(2.5, self.sv['sens'] + d)), 2)
        self.save()

    def tog_cam(self):
        self.sv['cam'] = 1 - self.sv['cam']
        self.save()
        self.build_ui()

    def tog_snd(self):
        self.sv['sound'] = 1 - self.sv['sound']
        self.save()
        self.build_ui()

    # ---------------- запуск уровней ----------------
    def start_level(self, i):
        self.lvl_idx = i
        self.level = LEVELS[i]
        for p in self.level.pads:
            p.visited = False
        self.begin_run()

    def start_endless(self):
        self.lvl_idx = -1
        self.level = Endless()
        self.begin_run()

    def begin_run(self):
        lv = self.level
        self.pl.reset(*lv.start)
        self.cp = lv.start
        self.t_run = 0.0
        self.pen = 0.0
        self.falls = 0
        self.vmax = 0.0
        self.cd = 3.0
        self.cd_last = 4
        self.progress = 0.0
        self.yaw_acc = 0.0
        self.yaw_rate = 0.0
        self.acc = 0.0
        self.parts = []
        self.trail = []
        self.toast = ('', 0.0, (255, 255, 255))
        self.new_best = False
        self.medal = None
        self.hint_t = 8.0 if self.lvl_idx == 0 else 0.0
        self.last_speed = 0.0
        self.gain_t = 0.0
        self.go('play')

    def restart(self):
        if self.level.endless:
            self.start_endless()
        else:
            self.start_level(self.lvl_idx)

    def resume(self):
        self.go('play')

    def to_menu(self):
        self.go('title' if self.level is None or self.level.endless else 'levels')

    def pause(self):
        if self.state == 'play':
            self.go('pause')

    # ---------------- ввод ----------------
    def play_buttons(self):
        W, H, u = self.W, self.H, self.u
        auto_j, auto_s = PRESETS[self.sv['preset']]
        out = {'pause': (W - 66 * u, 12 * u, 54 * u, 54 * u)}
        if not auto_s:
            out['L'] = (22 * u, H - 150 * u, 120 * u, 128 * u)
            out['R'] = (154 * u, H - 150 * u, 120 * u, 128 * u)
        if not auto_j:
            if auto_s:
                out['J'] = (22 * u, H - 190 * u, 210 * u, 168 * u)
            else:
                out['J'] = (W - 232 * u, H - 190 * u, 210 * u, 168 * u)
        return out

    @staticmethod
    def hit(rect, x, y):
        return rect[0] <= x <= rect[0] + rect[2] and rect[1] <= y <= rect[1] + rect[3]

    def ev_down(self, tid, x, y):
        if self.state == 'play':
            for name, r in self.play_buttons().items():
                if self.hit(r, x, y):
                    self.touches[tid] = {'role': name, 'x': x, 'y': y}
                    if name == 'J':
                        self.pl.buf = JUMP_BUFFER
                    return
            self.touches[tid] = {'role': 'turn', 'x': x, 'y': y}
            return
        for b in self.btns:
            if self.hit(b['rect'], x, y):
                self.touches[tid] = {'role': 'ui', 'btn': b}
                return

    def ev_move(self, tid, x, y):
        tc = self.touches.get(tid)
        if not tc:
            return
        if tc['role'] == 'turn' and self.state == 'play':
            dx = x - tc['x']
            self.yaw_acc += dx / float(min(self.W, self.H)) * 3.3 * self.sv['sens']
        tc['x'], tc['y'] = x, y

    def ev_up(self, tid, x, y):
        tc = self.touches.pop(tid, None)
        if not tc:
            return
        if tc['role'] == 'ui':
            if self.hit(tc['btn']['rect'], x, y):
                self.play('ui')
                tc['btn']['fn']()
        elif tc['role'] == 'pause':
            r = self.play_buttons()['pause']
            if self.hit(r, x, y):
                self.pause()

    def key_down(self, k):
        pg = self.pg
        self.keys.add(k)
        if self.state == 'play':
            if k in (pg.K_SPACE, pg.K_UP, pg.K_w):
                self.pl.buf = JUMP_BUFFER
            elif k in (pg.K_ESCAPE, pg.K_p) or k == getattr(pg, 'K_AC_BACK', -999):
                self.pause()
            elif k == pg.K_r:
                self.restart()
        elif self.state == 'pause' and (k in (pg.K_ESCAPE, pg.K_p) or k == getattr(pg, 'K_AC_BACK', -999)):
            self.resume()
        elif self.state in ('levels', 'help', 'settings') and (k == pg.K_ESCAPE or k == getattr(pg, 'K_AC_BACK', -999)):
            self.go('title')
        elif self.state in ('done', 'over') and (k == pg.K_ESCAPE or k == getattr(pg, 'K_AC_BACK', -999)):
            self.to_menu()
        elif self.state == 'title' and k == pg.K_ESCAPE:
            self.running = False

    def handle_events(self):
        pg = self.pg
        W, H = self.W, self.H
        sx, sy = W / float(self.dw), H / float(self.dh)
        for e in pg.event.get():
            tp = e.type
            if tp == pg.QUIT:
                self.running = False
            elif tp == pg.KEYDOWN:
                self.key_down(e.key)
            elif tp == pg.KEYUP:
                self.keys.discard(e.key)
            elif tp == getattr(pg, 'FINGERDOWN', -1):
                if not self.seen_finger:
                    self.seen_finger = True
                    self.touches.pop('m', None)
                self.ev_down(e.finger_id, e.x * W, e.y * H)
            elif tp == getattr(pg, 'FINGERMOTION', -1):
                self.ev_move(e.finger_id, e.x * W, e.y * H)
            elif tp == getattr(pg, 'FINGERUP', -1):
                self.ev_up(e.finger_id, e.x * W, e.y * H)
            elif tp == pg.MOUSEBUTTONDOWN and not self.seen_finger:
                self.ev_down('m', e.pos[0] * sx, e.pos[1] * sy)
            elif tp == pg.MOUSEMOTION and not self.seen_finger and 'm' in self.touches:
                self.ev_move('m', e.pos[0] * sx, e.pos[1] * sy)
            elif tp == pg.MOUSEBUTTONUP and not self.seen_finger:
                self.ev_up('m', e.pos[0] * sx, e.pos[1] * sy)

    # ---------------- игровая логика ----------------
    def toast_set(self, s, col=(255, 255, 255), t=1.4):
        self.toast = (s, t, col)

    def finish_run(self):
        total = self.t_run + self.pen
        self.final = total
        self.play('fin')
        if not self.level.endless:
            key = str(self.lvl_idx)
            best = self.sv['best'].get(key)
            if best is None or total < best:
                self.sv['best'][key] = round(total, 2)
                self.new_best = best is not None
            g, s, b = self.level.medals
            self.medal = 'gold' if total <= g else 'silver' if total <= s else 'bronze' if total <= b else None
            self.save()
        self.go('done')

    def game_over(self):
        sc = int(self.progress / 60.0)
        self.score = sc
        self.new_best = sc > self.sv['endless']
        if self.new_best:
            self.sv['endless'] = sc
            self.save()
        self.play('fall')
        self.go('over')

    def sync_view(self, strafe):
        """Помощник авто-стрейфа: держит взгляд под оптимальным углом к вектору скорости."""
        pl = self.pl
        sp = pl.speed
        if sp < 40:
            return
        phi = math.atan2(pl.vy, pl.vx)
        d = math.asin(min(1.0, (AIR_CAP - 0.9 * AIR_ACCEL * AIR_CAP * TICK) / sp))
        diff = wrap(phi - strafe * d - pl.yaw)
        pl.yaw += diff * min(1.0, ASSIST_RATE * TICK)

    def ground_check(self):
        """Прогресс, чекпоинты, финиш. Вызывается на каждом тике, пока игрок на земле."""
        pl, lv = self.pl, self.level
        pad = lv.pad_at(pl.x, pl.y, 0)
        if pad is None:
            return False
        pr = pad.s0 + max(0.0, pad.local_x(pl.x, pl.y))
        if pr > self.progress:
            self.progress = pr
        if pad.kind == 'cp' and not pad.visited:
            pad.visited = True
            self.cp = (pad.cx, pad.cy, pad.ang)
            self.toast_set(self.t('checkpoint'), (255, 220, 90))
            self.play('cp')
        elif pad.kind == 'finish':
            self.finish_run()
            return True
        return False

    def update_play(self, dt):
        pl, lv = self.pl, self.level
        auto_j, auto_s = PRESETS[self.sv['preset']]
        k = self.keys
        pg = self.pg
        # клавиатура
        turn_k = (1 if (pg.K_RIGHT in k) else 0) - (1 if (pg.K_LEFT in k) else 0)
        self.yaw_acc += turn_k * 1.9 * self.sv['sens'] * dt
        strafe_m = 0
        if pg.K_d in k:
            strafe_m += 1
        if pg.K_a in k:
            strafe_m -= 1
        for tc in self.touches.values():
            if tc['role'] == 'R':
                strafe_m += 1
            elif tc['role'] == 'L':
                strafe_m -= 1
        strafe_m = max(-1, min(1, strafe_m))
        # скорость поворота -> авто-стрейф
        inst = self.yaw_acc / max(dt, 1e-4)
        self.yaw_rate += (inst - self.yaw_rate) * min(1.0, dt / 0.06)
        if auto_s:
            strafe = 0 if abs(self.yaw_rate) < 0.3 else (1 if self.yaw_rate > 0 else -1)
        else:
            strafe = strafe_m
        if self.cd > 0:
            pl.yaw += self.yaw_acc
            self.yaw_acc = 0.0
            self.cd -= dt
            n = int(math.ceil(self.cd))
            if n != self.cd_last and self.cd > 0:
                self.cd_last = n
                self.play('tick')
            if self.cd <= 0 and self.t_run == 0:
                self.play('go')
                self.toast_set(self.t('go'), (120, 255, 160), 0.9)
            return
        self.t_run += dt
        steps = 0
        self.acc += dt
        n = int(self.acc / TICK)
        n = min(n, 12)
        self.acc = min(self.acc - n * TICK, TICK * 12)
        dyaw = self.yaw_acc / n if n else 0.0
        if n == 0:
            pl.yaw += self.yaw_acc
        self.yaw_acc = 0.0
        for _ in range(n):
            pl.yaw += dyaw
            if auto_s and strafe and not pl.ground:
                self.sync_view(strafe)
            pl.step(TICK, strafe, auto_j, True, lv)
            if pl.ev_jump:
                pl.ev_jump = False
                self.play('jump')
                if not auto_j and pl.hops > 0:
                    if pl.perfect:
                        self.toast_set(self.t('perfect'), (120, 255, 160), 0.6)
                        self.play('perfect')
                    elif pl.ground_t > 0.06:
                        self.toast_set(self.t('late'), (255, 170, 90), 0.5)
            if pl.ev_land:
                pl.ev_land = False
                if pl.speed > 250:
                    self.play('land')
                    for _i in range(5):
                        a = self.rng.random() * 6.283
                        sp = self.rng.uniform(40, 160)
                        self.parts.append([pl.x, pl.y, math.cos(a) * sp, math.sin(a) * sp, 0.5, speed_color(pl.speed)])
            if pl.ground and self.ground_check():
                return
            if pl.dead:
                break
        sp = pl.speed
        if sp > self.vmax:
            self.vmax = sp
        self.gain_t += dt
        if self.gain_t > 0.25:
            self.gain = sp - self.last_speed
            self.last_speed = sp
            self.gain_t = 0.0
        lv.update(pl.x, pl.y)
        # след
        if (not self.trail) or (self.trail[-1][0] - pl.x) ** 2 + (self.trail[-1][1] - pl.y) ** 2 > 400:
            self.trail.append((pl.x, pl.y, sp))
            if len(self.trail) > 40:
                self.trail.pop(0)
        for p in self.parts:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] -= dt
        self.parts = [p for p in self.parts if p[4] > 0]
        if pl.dead:
            if lv.endless:
                self.game_over()
            else:
                self.falls += 1
                self.pen += FALL_PENALTY
                self.toast_set(self.t('fall') % FALL_PENALTY, (255, 120, 110), 1.2)
                self.play('fall')
                pl.reset(*self.cp)
                self.trail = []
                self.cd = 0.7
                self.cd_last = 1
        if self.toast[1] > 0:
            self.toast = (self.toast[0], self.toast[1] - dt, self.toast[2])
        if self.hint_t > 0 and pl.speed > 0:
            self.hint_t -= dt

    # ---------------- отрисовка ----------------
    def cam_setup(self):
        pl = self.pl
        W, H = self.W, self.H
        sp = pl.speed
        target = (min(W, H) / 560.0) / (1.0 + sp / 1100.0)
        self.cam_scale += (target - self.cam_scale) * 0.06
        sc = self.cam_scale
        if self.sv['cam'] == 0:
            c, s = math.cos(pl.yaw), math.sin(pl.yaw)
            self.m = (-s * sc, c * sc, -c * sc, -s * sc)
            self.ax, self.ay = W / 2, H * 0.72
        else:
            self.m = (sc, 0.0, 0.0, sc)
            self.ax, self.ay = W / 2, H * 0.5
        self.cx, self.cy = pl.x, pl.y

    def proj(self, wx, wy):
        dx, dy = wx - self.cx, wy - self.cy
        m = self.m
        return (self.ax + dx * m[0] + dy * m[1], self.ay + dx * m[2] + dy * m[3])

    def draw_world(self):
        pg, scr = self.pg, self.scr
        W, H, u = self.W, self.H, self.u
        pl, lv = self.pl, self.level
        self.cam_setup()
        sc = self.cam_scale
        scr.fill((12, 16, 34))
        # сетка бездны
        R = math.hypot(W, H) / sc * 0.75
        gs = 260.0
        gx0 = int((self.cx - R) // gs)
        gx1 = int((self.cx + R) // gs) + 1
        gy0 = int((self.cy - R) // gs)
        gy1 = int((self.cy + R) // gs) + 1
        gcol = (22, 28, 58)
        for gx in range(gx0, gx1 + 1):
            pg.draw.line(scr, gcol, self.proj(gx * gs, self.cy - R), self.proj(gx * gs, self.cy + R), 1)
        for gy in range(gy0, gy1 + 1):
            pg.draw.line(scr, gcol, self.proj(self.cx - R, gy * gs), self.proj(self.cx + R, gy * gs), 1)
        # платформы
        thick = 16 * u
        for p in lv.pads:
            dd = (p.cx - self.cx) ** 2 + (p.cy - self.cy) ** 2
            lim = R + p.rad
            if dd > lim * lim:
                continue
            pts = [self.proj(x, y) for x, y in p.corners()]
            if p.kind == 'start':
                top, side, edge = (44, 150, 100), (24, 80, 56), (120, 240, 170)
            elif p.kind == 'cp':
                top, side, edge = (222, 176, 56), (120, 90, 24), (255, 232, 130)
            elif p.kind == 'finish':
                top, side, edge = (236, 236, 246), (130, 130, 150), (255, 90, 150)
            else:
                top, side, edge = (58, 76, 118), (28, 38, 68), (110, 140, 205)
            pg.draw.polygon(scr, side, [(x, y + thick) for x, y in pts])
            pg.draw.polygon(scr, top, pts)
            # поперечные полосы (для ощущения скорости)
            stripe = tuple(min(255, c + 22) for c in top)
            k = 1
            L = p.hl * 2
            while k * 110.0 < L:
                lx = -p.hl + k * 110.0
                a = (p.cx + lx * p.c + p.hw * 0.92 * (-p.s), p.cy + lx * p.s + p.hw * 0.92 * p.c)
                b = (p.cx + lx * p.c - p.hw * 0.92 * (-p.s), p.cy + lx * p.s - p.hw * 0.92 * p.c)
                pg.draw.line(scr, stripe, self.proj(*a), self.proj(*b), 2)
                k += 1
            if p.kind == 'finish':
                for j in range(-3, 4):
                    ww = p.hw * 2 / 7.0
                    a = (p.cx + (-p.hl + 40) * p.c + (j * ww) * (-p.s), p.cy + (-p.hl + 40) * p.s + (j * ww) * p.c)
                    b = (p.cx + (p.hl - 40) * p.c + (j * ww) * (-p.s), p.cy + (p.hl - 40) * p.s + (j * ww) * p.c)
                    pg.draw.line(scr, (255, 90, 150), self.proj(*a), self.proj(*b), 3)
            pg.draw.polygon(scr, edge, pts, 2)
        # след
        if len(self.trail) > 1:
            for i in range(1, len(self.trail)):
                a, b = self.trail[i - 1], self.trail[i]
                pg.draw.line(scr, speed_color(b[2]), self.proj(a[0], a[1]), self.proj(b[0], b[1]), max(2, int(5 * u * i / len(self.trail))))
        # частицы
        for p in self.parts:
            x, y = self.proj(p[0], p[1])
            pg.draw.circle(scr, p[5], (int(x), int(y)), max(1, int(3 * u * p[4] * 2)))
        # игрок
        ax, ay = self.ax, self.ay
        lift = pl.z * sc * 0.55
        sh_r = max(5, int(PLAYER_R * sc * 1.3 * (1.0 - min(0.6, pl.z / 600.0))))
        pg.draw.circle(scr, (6, 8, 18), (int(ax), int(ay)), sh_r)
        body = max(8, int(PLAYER_R * sc * 1.5))
        col = speed_color(pl.speed)
        pg.draw.circle(scr, (240, 244, 255), (int(ax), int(ay - lift)), body)
        pg.draw.circle(scr, col, (int(ax), int(ay - lift)), body, max(2, int(3 * u)))
        # направление взгляда
        if self.sv['cam'] == 0:
            dvx, dvy = 0.0, -1.0
        else:
            dvx, dvy = math.cos(pl.yaw), math.sin(pl.yaw)
        pg.draw.line(scr, (255, 255, 255), (ax, ay - lift), (ax + dvx * body * 2.2, ay - lift + dvy * body * 2.2), max(2, int(3 * u)))
        # вектор скорости
        m = self.m
        vsx = pl.vx * m[0] + pl.vy * m[1]
        vsy = pl.vx * m[2] + pl.vy * m[3]
        ln = math.hypot(vsx, vsy)
        if ln > 4:
            k = min(1.0, (H * 0.28) / ln)
            pg.draw.line(scr, (80, 170, 255), (ax, ay - lift), (ax + vsx * k * 0.5, ay - lift + vsy * k * 0.5), max(3, int(4 * u)))
            pg.draw.circle(scr, (80, 170, 255), (int(ax + vsx * k * 0.5), int(ay - lift + vsy * k * 0.5)), max(4, int(6 * u)))
        # линии скорости
        if pl.speed > 480:
            r = self.rng
            for _ in range(8):
                a = r.random() * 6.283
                r1 = (0.55 + r.random() * 0.2) * H
                r2 = r1 + 40 * u + (pl.speed - 480) * 0.12
                pg.draw.line(scr, (70, 90, 160), (W / 2 + math.cos(a) * r1 * 1.3, H / 2 + math.sin(a) * r1),
                             (W / 2 + math.cos(a) * r2 * 1.3, H / 2 + math.sin(a) * r2), 2)

    def draw_play_ui(self):
        pg, scr = self.pg, self.scr
        W, H, u = self.W, self.H, self.u
        pl = self.pl
        sp = pl.speed
        col = speed_color(sp)
        # скорость
        self.text('%d' % sp, 54, col, W / 2, 48 * u)
        self.text(self.t('speed') + ' u/s', 15, (170, 180, 210), W / 2, 84 * u, bold=False)
        gain = getattr(self, 'gain', 0.0)
        if gain > 6:
            self.text('+%d' % gain, 20, (120, 255, 160), W / 2 + 86 * u, 52 * u)
        elif gain < -20 and pl.ground is False:
            self.text('%d' % gain, 20, (255, 130, 120), W / 2 + 86 * u, 52 * u)
        # полоса скорости
        bw = 300 * u
        bx, by = W / 2 - bw / 2, 100 * u
        pg.draw.rect(scr, (30, 36, 70), (bx, by, bw, 8 * u))
        pg.draw.rect(scr, col, (bx, by, bw * min(1.0, sp / 1000.0), 8 * u))
        # время
        tot = self.t_run + self.pen
        m, s = divmod(tot, 60)
        if self.level.endless:
            self.text('%s: %d' % (self.t('dist'), int(self.progress / 60.0)), 24, (230, 235, 255), 18 * u, 30 * u, 'l')
        else:
            self.text('%d:%05.2f' % (m, s), 30, (230, 235, 255), 18 * u, 30 * u, 'l')
            self.text(self.level.name, 15, (150, 160, 200), 18 * u, 60 * u, 'l', False)
            if self.falls:
                self.text('%s: %d' % (self.t('falls'), self.falls), 15, (255, 140, 130), 18 * u, 82 * u, 'l', False)
            # прогресс уровня
            pg.draw.rect(scr, (30, 36, 70), (18 * u, 100 * u, 160 * u, 6 * u))
            pg.draw.rect(scr, (110, 200, 255), (18 * u, 100 * u, 160 * u * min(1.0, self.progress / max(1.0, self.level.total)), 6 * u))
        # кнопки
        pb = self.play_buttons()
        r = pb['pause']
        scr.blit(self.alpha_box(r[2], r[3], (255, 255, 255), 60, 10), (r[0], r[1]))
        pg.draw.rect(scr, (255, 255, 255), (r[0] + r[2] * 0.32, r[1] + r[3] * 0.25, r[2] * 0.13, r[3] * 0.5))
        pg.draw.rect(scr, (255, 255, 255), (r[0] + r[2] * 0.55, r[1] + r[3] * 0.25, r[2] * 0.13, r[3] * 0.5))
        active = set(tc['role'] for tc in self.touches.values())
        for name in ('L', 'R', 'J'):
            if name not in pb:
                continue
            r = pb[name]
            a = 120 if name in active else 55
            scr.blit(self.alpha_box(r[2], r[3], (255, 255, 255), a, 24), (r[0], r[1]))
            cx, cy = r[0] + r[2] / 2, r[1] + r[3] / 2
            if name == 'J':
                self.text(self.t('jump'), 28, (255, 255, 255), cx, cy)
            else:
                d = -1 if name == 'L' else 1
                tri = [(cx + d * 26 * u, cy), (cx - d * 18 * u, cy - 28 * u), (cx - d * 18 * u, cy + 28 * u)]
                pg.draw.polygon(scr, (255, 255, 255), tri)
        # плашка с подсказкой
        auto_j, auto_s = PRESETS[self.sv['preset']]
        if self.hint_t > 0 and self.cd <= 0:
            tw = self.text(self.t('hint1'), 22, (255, 255, 255), W / 2, H * 0.36)
        # отсчёт
        if self.cd > 0 and self.t_run == 0:
            n = int(math.ceil(self.cd))
            self.text(str(n), 120, (255, 255, 255), W / 2, H * 0.34)
        elif self.cd > 0:
            pass
        # тост
        if self.toast[1] > 0 and self.toast[0]:
            self.text(self.toast[0], 34, self.toast[2], W / 2, H * 0.26)

    def draw_menu_bg(self, title=None):
        scr = self.scr
        W, H, u = self.W, self.H, self.u
        scr.fill((12, 16, 34))
        for i in range(-3, 18):
            x = (i * 120 * u + (time.time() * 40 * u) % (120 * u))
            self.pg.draw.line(scr, (22, 28, 58), (x, 0), (x - H * 0.4, H), 2)
        if title:
            self.text(title, 40, (240, 244, 255), W / 2, H * 0.09)

    def draw_buttons(self):
        scr = self.scr
        u = self.u
        for b in self.btns:
            r = b['rect']
            style = b['style']
            pressed = any(tc.get('btn') is b for tc in self.touches.values())
            cols = {0: (60, 130, 255), 1: (44, 52, 96), 2: (36, 44, 84), 3: (50, 160, 110)}
            col = cols.get(style, (44, 52, 96))
            if pressed:
                col = tuple(min(255, c + 40) for c in col)
            self.rrect(col, r, 14)
            self.rrect((110, 130, 210), r, 14, 2)
            cx, cy = r[0] + r[2] / 2, r[1] + r[3] / 2
            if b['sub']:
                self.text(b['label'], b['size'], (255, 255, 255), r[0] + 16 * u, r[1] + r[3] * 0.32, 'l')
                self.text(b['sub'], 13, (170, 182, 225), r[0] + 16 * u, r[1] + r[3] * 0.64, 'l', False)
                best = self.sv['best'].get(str(LEVELS_IDX.get(b['label'], -1)))
                if best is not None:
                    lv = LEVELS[LEVELS_IDX[b['label']]]
                    g, s, bz = lv.medals
                    mc = (255, 205, 60) if best <= g else (205, 210, 220) if best <= s else (205, 130, 70) if best <= bz else (120, 130, 160)
                    self.pg.draw.circle(scr, mc, (int(r[0] + r[2] - 30 * u), int(r[1] + 28 * u)), int(12 * u))
                    self.text('%.1f' % best, 14, (230, 235, 255), r[0] + r[2] - 14 * u, r[1] + r[3] - 22 * u, 'r', False)
            else:
                self.text(b['label'], b['size'], (255, 255, 255), cx, cy)

    def draw_ui_state(self):
        scr = self.scr
        W, H, u = self.W, self.H, self.u
        t = self.t
        st = self.state
        if st == 'title':
            self.draw_menu_bg()
            self.text('BHOP', 96, (240, 244, 255), W / 2, H * 0.16)
            self.text(t('sub'), 22, (130, 170, 255), W / 2, H * 0.27, bold=False)
            self.text(t('p%d' % self.sv['preset']), 15, (150, 160, 200), W / 2, H - 22 * u, bold=False)
            if self.sv['endless']:
                self.text('%s: %d' % (t('endless'), self.sv['endless']), 15, (150, 160, 200), W / 2, H - 44 * u, bold=False)
        elif st == 'levels':
            self.draw_menu_bg(t('levels'))
        elif st == 'help':
            self.draw_menu_bg(t('help'))
            y = H * 0.17
            for i in range(6):
                for line in self.wrap(t('h%d' % i), 16, W * 0.88):
                    self.text(line, 16, (225, 232, 255), W / 2, y, bold=False)
                    y += 23 * u
                y += 9 * u
        elif st == 'settings':
            self.draw_menu_bg(t('settings'))
            y2 = H * 0.18 + 4 * 66 * u + 14 * u
            self.text(t('sens') + ': %.2f' % self.sv['sens'], 21, (230, 235, 255), self.W / 2 - 150 * u, y2 + 25 * u, 'c', False)
        elif st in ('pause', 'done', 'over'):
            self.draw_world()
            dim = self.pg.Surface((W, H))
            dim.set_alpha(150)
            scr.blit(dim, (0, 0))
            if st == 'pause':
                self.text(t('paused'), 54, (255, 255, 255), W / 2, H * 0.2)
            elif st == 'done':
                self.text(t('finish'), 58, (255, 255, 255), W / 2, H * 0.14)
                m_, s_ = divmod(self.final, 60)
                self.text('%s  %d:%05.2f' % (t('time'), m_, s_), 36, (255, 255, 255), W / 2, H * 0.28)
                self.text('%s %d   (+%d с)' % (t('falls'), self.falls, int(self.pen)) if self.lang == 'ru' else '%s %d   (+%ds)' % (t('falls'), self.falls, int(self.pen)),
                          19, (200, 210, 240), W / 2, H * 0.37, bold=False)
                self.text('%s %d u/s' % (t('maxspeed'), self.vmax), 19, (200, 210, 240), W / 2, H * 0.43, bold=False)
                if self.medal:
                    mc = {'gold': (255, 205, 60), 'silver': (205, 210, 220), 'bronze': (205, 130, 70)}[self.medal]
                    self.pg.draw.circle(scr, mc, (int(W / 2), int(H * 0.55)), int(34 * u))
                    self.text(t(self.medal), 24, mc, W / 2, H * 0.66)
                if self.new_best:
                    self.text(t('new'), 24, (120, 255, 160), W / 2, H * 0.50 if not self.medal else H * 0.47)
            else:
                self.text(t('over'), 58, (255, 255, 255), W / 2, H * 0.16)
                self.text('%s: %d' % (t('dist'), self.score), 40, (255, 255, 255), W / 2, H * 0.32)
                self.text('%s: %d' % (t('best'), self.sv['endless']), 22, (200, 210, 240), W / 2, H * 0.44, bold=False)
                if self.new_best:
                    self.text(t('new'), 26, (120, 255, 160), W / 2, H * 0.54)
        self.draw_buttons()

    def draw(self):
        if self.state == 'play':
            self.draw_world()
            self.draw_play_ui()
        else:
            self.draw_ui_state()
        if self.scale_needed:
            self.pg.transform.scale(self.scr, (self.dw, self.dh), self.disp)
        self.pg.display.flip()

    def run(self):
        self.running = True
        last = time.time()
        while self.running:
            now = time.time()
            dt = min(0.05, max(0.001, now - last))
            last = now
            self.handle_events()
            if self.state == 'play':
                self.update_play(dt)
            self.draw()
            self.clock.tick(60)
        self.pg.quit()


LEVELS_IDX = dict((lv.name, i) for i, lv in enumerate(LEVELS))


def main():
    import pygame
    try:
        pygame.mixer.pre_init(22050, -16, 1, 512)
    except Exception:
        pass
    App(pygame).run()


if __name__ == '__main__':
    main()
 