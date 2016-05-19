import uuid
from flask import Flask, render_template, request
from flask.ext.socketio import SocketIO, send, emit, join_room, leave_room

app = Flask(__name__)
socketio = SocketIO(app)

class ActiveGame (object):
    
    _games = {}
    _sessions = {}
    
    _filtered = set()
    
    @staticmethod
    def getFiltered():
        r = set()
        for i in range(0, 26):
            r.add(chr(ord('A') + i))
        return r
    
    @staticmethod
    def getGame(gid):
        try:
            return ActiveGame._games[gid]
        except KeyError:
            return None
    
    @staticmethod
    def registerGame(g):
        if g.gid in ActiveGame._games:
            raise Exception()
        ActiveGame._games[g.gid] = g
    
    @staticmethod
    def destroyGame(gid):
        if gid in ActiveGame._games:
            del ActiveGame._games[gid]
        
    @staticmethod
    def handleDisconnect(sid):
        if sid in ActiveGame._sessions:
            # find game
            g = ActiveGame._sessions[sid]
            
            # remove this user from the game
            if sid == g.p1:
                g.p1 = None
                other = 2
            elif sid == g.p2:
                g.p2 = None
                other = 1
            del ActiveGame._sessions[sid]
            
            # alert other users that the player has left
            emit("waiting", other, room=g.gid)
            
            # remove game if it is now empty
            if g.empty():
                ActiveGame.destroyGame(g.gid)
                
    def __init__(self, gid):
        self.gid = gid
        self.p1 = None
        self.p2 = None
        self.word = None
        self.guesses = []
        self.attempts = 6
        self.r1 = False
        self.r2 = False
        ActiveGame.registerGame(self)
    
    def reset(self):
        self.word = None
        self.guesses = []
        self.attempts = 6
        self.r1 = False
        self.r2 = False
    
    def swap(self):
        self.p1, self.p2 = self.p2, self.p1
    
    def join(self, sid):
        if self.p1 is None:
            self.p1 = sid
            ActiveGame._sessions[sid] = self
            return 1
        elif self.p2 is None:
            self.p2 = sid
            ActiveGame._sessions[sid] = self
            return 2
        else:
            return 0
    
    def ready(self):
        return self.p1 is not None and self.p2 is not None
    
    def empty(self):
        return self.p1 is None and self.p2 is None
    
    def chooseWord(self, w):
        w = w.upper()
        if self.word is not None:
            return False
        self.word = w
        return True
    
    def getCleanWord(self):
        ret = []
        for char in self.word:
            if char in ActiveGame._filtered and not char in self.guesses:
                ret.append("_")
            else:
                ret.append(char)
                
        return "".join(ret)
    
    def makeGuess(self, letter):
        letter = letter.upper()
        if self.attempts == 0:
            return False
        if not letter in ActiveGame._filtered:
            return False
        if letter in self.guesses:
            return False
        if not letter in self.word:
            self.attempts -= 1
        self.guesses.append(letter)
        return True
    
    def getGameState(self, clean=False):
        r = {
            'guesses':   list(self.guesses),
            'attempts':  self.attempts,
            'word':      None,
            'cleanword': None,
            'winner':    None
        }
        
        if self.word is not None:
            r['cleanword'] = self.getCleanWord()
            r['word'] = r['cleanword'] if (clean and self.attempts > 0) else self.word
        
            if all(s in self.guesses or not s in ActiveGame._filtered for s in self.word):
                r['winner'] = 2
            
            if self.attempts == 0:
                r['winner'] = 1
        
        return r
        
    
ActiveGame._filtered = ActiveGame.getFiltered()

@app.route('/')
def main():
    return render_template('index.html')

@app.route('/play')
def play():
    return render_template('play.html')

@socketio.on('connect')
def ws_conn():
    pass

@socketio.on('disconnect')
def ws_disconn():
    ActiveGame.handleDisconnect(request.sid)

@socketio.on('newgame')
def ws_ngurl():
    emit('newgame', uuid.uuid4().hex[:8])

@socketio.on('join')
def ws_join(room):
    g = ActiveGame.getGame(room)
    
    if g is None:
        g = ActiveGame(room)
    
    status = g.join(request.sid)
    
    if status == 0:
        emit("error", "game already in progress")
        return
    else:
        join_room(room)
        emit("waiting", status)
        
    if g.ready():
        emit("ready", room=room)

@socketio.on('getstat')
def ws_getstat(room):
    g = ActiveGame.getGame(room)
    if g is None:
        emit("error", "game not in progress")
        return
    emit("status", g.getGameState(g.p1 != request.sid))

@socketio.on('word')
def ws_word(room, word):
    g = ActiveGame.getGame(room)
    
    if g is None:
        emit("error", "game not in progress")
        return
    
    if g.p1 != request.sid:
        emit("error", "you are not player 1")
        return
    
    if g.chooseWord(word):
        emit("refresh", room=room)
    else:
        emit("error", "word already chosen")

@socketio.on('guess')
def ws_guess(room, guess):
    g = ActiveGame.getGame(room)
    
    if g is None:
        emit("error", "game not in progress")
        return
    
    if g.p2 != request.sid:
        emit("error", "you are not player 2")
        return
    
    if g.makeGuess(guess):
        emit("refresh", room=room)
    else:   
        emit("badguess")
    
@socketio.on('rematch')
def ws_rematch(room):
    g = ActiveGame.getGame(room)
    
    if g is None:
        emit("error", "game not in progress")
        return
    
    if g.p1 == request.sid:
        g.r1 = True
    
    if g.p2 == request.sid:
        g.r2 = True
    
    if g.r1 and g.r2:
        g.swap()
        g.reset()
        emit('swap', room=room)
    else:
        emit('rematch', room=room)

if __name__ == "__main__":
    socketio.run(app, "0.0.0.0", port=5000)
