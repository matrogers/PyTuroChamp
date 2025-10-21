#!/usr/bin/env python3

# XBoard/UCI interface to PyTuroChamp

from __future__ import print_function
import sys, datetime, os, threading, time
import chess as c
import chess.pgn

abc = "abcdefgh"
nn = "12345678"
is_uci = True

PGN_ENABLE = os.getenv("PTC_PGN", "0").lower() in ("1","true","yes","on")

# --- Unbuffered stdout so GUI sees bestmove immediately ---
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

# --- Engine selection ---
if sys.argv[-1] == 'newt':
    import newt as p
    lf = "Newt-log.txt"; mf = "Newt.pgn"; nm = "Newt"
elif sys.argv[-1] == 'ptc':
    import pyturochamp as p
    lf = "PyTuroChamp-log.txt"; mf = "PyTuroChamp.pgn"; nm = "PyTuroChamp"
elif sys.argv[-1] == 'bare':
    import bare as p
    lf = "Bare-log.txt"; mf = "Bare.pgn"; nm = "Bare"
elif sys.argv[-1] == 'plan':
    import plan as p
    lf = "Plan-log.txt"; mf = "Plan.pgn"; nm = "Plan"
elif sys.argv[-1] == 'shannon':
    import shannon as p
    lf = "Shannon-log.txt"; mf = "Shannon.pgn"; nm = "Shannon"
elif sys.argv[-1] == 'soma':
    import soma as p
    lf = "SOMA-log.txt"; mf = "SOMA.pgn"; nm = "SOMA"
elif sys.argv[-1] == 'torres':
    import torres as p
    lf = "Torres-log.txt"; mf = "Torres.pgn"; nm = "El Ajedrecista"
elif sys.argv[-1] == 'bern':
    import bernstein as p
    lf = "Bernstein-log.txt"; mf = "Bernstein.pgn"; nm = "Bernstein"
elif sys.argv[-1] == 'rmove':
    import rmove as p
    lf = "RMove-log.txt"; mf = "RMove.pgn"; nm = "Random Mover"
elif sys.argv[-1] == 'adapt':
    import adapt as p
    lf = "Adapt-log.txt"; mf = "Adapt.pgn"; nm = "Simple Adaptive Engine"
else:
    if 'linux' in sys.platform:
        import pyturochamp_multi as p
        lf = "PyTuroChamp-log.txt"; mf = "PyTuroChamp.pgn"; nm = "PyTuroChamp Multi-Core"
    else:
        import pyturochamp as p
        lf = "PyTuroChamp-log.txt"; mf = "PyTuroChamp.pgn"; nm = "PyTuroChamp"

p.Chess960 = False  # Chess960 mode off by default

# --- Optional logging ---
LOG_ENABLE = os.getenv("PTC_LOG", "0").lower() in ("1","true","yes","on")
LOG_PATH = os.getenv("PTC_LOG_FILE", "")
try:
    log = open(LOG_PATH or lf, 'w') if LOG_ENABLE else None
except:
    log = None
    print("# Could not create log file")

def print2(x):
    print(x, flush=True)
    if log:
        log.write("< %s\n" % x)
        log.flush()

d = ''
search_thread = None
stop_flag = False
last_result = None  # holds latest (t, r) from p.getmove

# ========================
# Search functions
# ========================

def _think_loop(depth_target=None):
    """
    Iterative deepening: increase p.MAXPLIES from 1 up to depth_target (or 64 if None).
    Emits bestmove when done if not interrupted.
    """
    global last_result, stop_flag
    max_d = depth_target if depth_target is not None else 64
    if not d:
        newgame()
    for dd in range(1, max_d + 1):
        if stop_flag:
            return
        try:
            p.MAXPLIES = dd
        except Exception:
            pass
        t_res, r_res = p.getmove(d, silent=True)
        if r_res:
            last_result = (t_res, r_res)
        if stop_flag:
            return
    # finished normally -> emit bestmove
    if last_result and last_result[1]:
        move(last_result[1])
    else:
        print2("bestmove 0000" if is_uci else "move 0000")

def start_search(go_line):
    """
    Parse 'go ...' line and decide between synchronous (depth only) and async search.
    """
    global search_thread, stop_flag, last_result
    stop_flag = False
    last_result = None
    depth = None
    movetime = None
    wtime = btime = None
    toks = go_line.split()
    if "depth" in toks:
        try: depth = int(toks[toks.index("depth")+1])
        except Exception: depth = None
    if "movetime" in toks:
        try: movetime = int(toks[toks.index("movetime")+1])
        except Exception: movetime = None
    if "wtime" in toks:
        try: wtime = int(toks[toks.index("wtime")+1])
        except Exception: wtime = None
    if "btime" in toks:
        try: btime = int(toks[toks.index("btime")+1])
        except Exception: btime = None

    # Fast path: go depth N, no timers
    if depth is not None and movetime is None and wtime is None and btime is None:
        try:
            p.MAXPLIES = depth
        except Exception:
            try: p.DEPTH = depth
            except Exception: pass
        t_res, r_res = p.getmove(d, silent=True)
        if r_res:
            move(r_res)
        else:
            print2("bestmove 0000")
        return

    # Otherwise: background search
    search_thread = threading.Thread(target=_think_loop, args=(depth,), daemon=True)
    search_thread.start()

def stop_search_and_output():
    """
    Set stop flag, join, and output the last stored bestmove (if any).
    """
    global stop_flag, search_thread, last_result
    stop_flag = True
    if search_thread is not None:
        search_thread.join(timeout=0.2)
        search_thread = None
    if last_result and last_result[1]:
        move(last_result[1])
    else:
        print2("bestmove 0000" if is_uci else "move 0000")

# ========================
# Game handling
# ========================

def move(r):
    rm = r[0]
    d.push_uci(rm)
    print2("bestmove %s" % rm if is_uci else "move %s" % rm)
    pgn()

def pgn():
    if not PGN_ENABLE:
        return

    game = chess.pgn.Game.from_board(d)
    now = datetime.datetime.now()
    game.headers["Date"] = now.strftime("%Y.%m.%d")
    if p.COMPC == c.WHITE:
        game.headers["White"] = nm
        game.headers["Black"] = "User"
    else:
        game.headers["Black"] = nm
        game.headers["White"] = "User"
    if PGN_ENABLE:
        try:
            with open(mf, 'w') as f:
                f.write(str(game) + '\n\n\n')
        except:
            print2("# Could not write PGN file")

def newgame():
    global d
    if p.Chess960:
        d = c.Board(chess960=True)
    else:
        d = c.Board()

def fromfen(fen):
    global d
    try:
        if p.Chess960:
            d = c.Board(fen, chess960=True)
        else:
            d = c.Board(fen)
    except:
        print2("Bad FEN")

def set_newt_time(line):
    xx = line.split()
    for x in range(len(xx)):
        if xx[x] == 'wtime': p.wtime = int(xx[x+1])
        if xx[x] == 'btime': p.btime = int(xx[x+1])
        if xx[x] == 'movestogo': p.movestogo = int(xx[x+1])
        if xx[x] == 'movetime': p.movetime = int(xx[x+1])
        if xx[x] == 'nodes': p.MAXNODES = int(xx[x+1])

# ========================
# Main loop
# ========================

while True:
    l = ''
    try:
        l = input() if sys.version >= '3' else raw_input()
    except KeyboardInterrupt:
        if not is_uci:
            pass
    if l:
        if log:
            log.write(l + '\n'); log.flush()

        if l == 'xboard':
            is_uci = False
            print2('feature myname="%s" setboard=1 done=1' % nm)

        elif l == 'quit':
            stop_flag = True
            if search_thread is not None:
                search_thread.join(timeout=0.2)
            sys.exit(0)

        elif l == 'new':
            stop_search_and_output()
            newgame()

        elif l == 'uci':
            is_uci = True
            print2(f"id name {nm}")
            print2("id author Martin C. Doege")
            # (options unchanged for brevity)
            if nm != 'Simple Adaptive Engine':
                print2("option name UCI_Chess960 type check default false")
            print2("uciok")

        elif l == 'ucinewgame':
            stop_search_and_output()
            newgame()

        elif 'position startpos moves' in l:
            mm = l.split()[3:]
            newgame()
            for mo in mm: d.push_uci(mo)

        elif 'position fen' in l:
            if l.split()[6] == 'moves':
                l = ' '.join(l.split()[:6] + ['0', '1'] + l.split()[6:])
            ff = ' '.join(l.split()[2:8])
            mm = l.split()[9:]
            if d:
                old = d.copy(); fromfen(ff)
                if old.fen() == ff:
                    for mo in mm: old.push_uci(mo)
                    d = old.copy()
                else:
                    for mo in mm: d.push_uci(mo)
            else:
                fromfen(ff)
                for mo in mm: d.push_uci(mo)

        elif l == 'isready':
            if not d: newgame()
            print2("readyok")

        elif 'setboard' in l:
            fen = l.split(' ', 1)[1]
            fromfen(fen)

        elif l[:2] == 'go':
            if not d: newgame()
            if nm == 'Newt': set_newt_time(l)
            start_search(l)

        elif l == 'stop' or l == 'force' or l == '?':
            stop_search_and_output()
            if log:
                log.write("move %s\n" % (last_result[1] if last_result else "0000"))
                log.flush()

        else:
            if not d: newgame()
            if len(l) >= 4 and l[0] in abc and l[2] in abc and l[1] in nn and l[3] in nn:
                if len(l) == 6:
                    l = l[:4] + 'q'
                d.push_uci(l)
                pgn()
                t, r = p.getmove(d, silent=True)
                if r:
                    move(r)
