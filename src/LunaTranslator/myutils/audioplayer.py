import time
from traceback import print_exc
from myutils.config import globalconfig
from myutils.wrapper import threader
import threading, types
import NativeUtils


class playonce:
    @threader
    def ___push_data_thread(self, data: "types.GeneratorType[bytes]", volume):
        for i, d in enumerate(data):
            if i == 0:
                self.handle = NativeUtils.bass_stream_handle_create(d, len(d))
                if not NativeUtils.bass_handle_play(self.handle, volume):
                    return
                self.idle = False
            elif not NativeUtils.bass_stream_push_data(self.handle, d, len(d)):
                break
        NativeUtils.bass_stream_push_data(self.handle, None, 0)

    def __init__(self, fileormem, volume) -> None:
        self.handle = 0
        self.idle = True
        self.paused = False
        self.__play(fileormem, volume)

    def __del__(self):
        _ = self.handle
        self.handle = 0
        NativeUtils.bass_handle_free(_)

    @property
    def isplaying(self):
        return NativeUtils.bass_handle_isplaying(self.handle)

    def pause(self):
        if not self.handle or self.idle or self.paused:
            return False
        if NativeUtils.bass_handle_pause(self.handle):
            self.paused = True
            return True
        return False

    def resume(self):
        if not self.handle or self.idle or not self.paused:
            return False
        if NativeUtils.bass_handle_resume(self.handle, False):
            self.paused = False
            return True
        return False

    def toggle_pause(self):
        return self.resume() if self.paused else self.pause()

    @threader
    def __play(self, data: "bytes | str | types.GeneratorType[bytes]", volume):
        if isinstance(data, (bytes, str)):
            self.handle = NativeUtils.bass_handle_create(
                data, len(data), isinstance(data, bytes)
            )
            if not NativeUtils.bass_handle_play(self.handle, volume):
                return
            self.idle = False
        elif isinstance(data, types.GeneratorType):
            self.___push_data_thread(data, volume)


def bass_code_cast(bs, fr="mp3"):
    # fr没啥用，仅用来给出编码失败时的用来占位的后缀，以少写代码
    to = globalconfig.get("audioformat", "mp3")
    ret = NativeUtils.bass_code_cast(
        bs, to, globalconfig.get("mp3kbps", 64), globalconfig.get("opusbitrate", 10)
    )
    if not ret:
        return bs, fr
    ext = {"mp3": "mp3", "opus": "ogg"}[to]
    return ret, ext


class series_audioplayer:
    def __init__(self, playovercallback=None):
        self.i = 0
        self.playovercallback = playovercallback
        self.lastfile = None
        self.tasks = None
        self.lock = threading.Lock()
        self.lock.acquire()
        self.timestamp = None
        self.lastcontext = None
        self.current = None
        self.current_lock = threading.Lock()
        self.__dotasks()

    def stop(self):
        self.timestamp = None
        try:
            self.tasks = (None, 0, True)
            self.lock.release()
        except:
            pass

    def play(self, binary, volume=100, force=False, timestamp=None):
        if timestamp and (timestamp != self.timestamp):
            return
        self.timestamp = timestamp
        try:
            self.tasks = (binary, volume, force)
            self.lock.release()
        except:
            pass

    def toggle_pause(self):
        with self.current_lock:
            if self.current is None:
                return False
            return self.current.toggle_pause()

    @threader
    def __dotasks(self):
        try:
            while True:
                self.lock.acquire()
                task = self.tasks
                self.tasks = None
                if task is None:
                    continue
                binary, volume, force = task
                _playonce = None
                if not binary:
                    continue
                _playonce = playonce(binary, volume)
                with self.current_lock:
                    self.current = _playonce
                while _playonce.idle and not self.tasks:
                    time.sleep(0.1)
                while _playonce.isplaying or _playonce.paused:
                    time.sleep(0.1)
                    if self.tasks and not (
                        globalconfig.get("ttsnointerrupt", False)
                        and (not self.tasks[-1])
                    ):
                        break
                else:
                    if self.playovercallback:
                        self.playovercallback(force)
                with self.current_lock:
                    if self.current is _playonce:
                        self.current = None
        except:
            print_exc()
