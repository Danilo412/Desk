"""Explicit local MP4 recording with a bounded, nonblocking latest-frame mailbox."""
from collections import deque
from fractions import Fraction
from pathlib import Path
import os,secrets,threading,time
from PIL import Image,ImageOps


class VideoRecorder:
    def __init__(self,path,event=lambda *a:None,fps=30,max_width=2560,audio=False):
        self.path=Path(path).resolve();self.event=event;self.fps=fps;self.max_width=max_width;self.audio=audio
        if fps not in (15,30) or max_width not in (1920,2560):raise ValueError('Perfil de gravação inválido.')
        if self.path.suffix.lower()!='.mp4':raise ValueError('Escolha um arquivo MP4.')
        self.id=secrets.token_hex(8);self.condition=threading.Condition();self.latest=None;self.audio_queue=deque()
        self.origin=None;self.pause_start=None;self.paused_total=0.;self._stop=False;self.finished=threading.Event()
        self.thread=None;self.frames=0;self.audio_samples=0;self.audio_received_samples=0;self.result=None;self.warning='';self.size=None
        self.audio_next_time=None;self.audio_last_wall=None;self.audio_epoch=0

    @property
    def paused(self):return self.pause_start is not None

    @property
    def elapsed(self):
        if self.origin is None:return 0.
        return max(0.,(self.pause_start or time.monotonic())-self.origin-self.paused_total)

    def start(self):
        if self.thread is not None:raise RuntimeError('Esta gravação já foi iniciada.')
        self.thread=threading.Thread(target=self._run,name='Desk MP4',daemon=False);self.thread.start();return self

    def offer(self,image):
        if not isinstance(image,Image.Image) or image.width<1 or image.height<1 or image.width*image.height>3840*2160:return False
        with self.condition:
            if self._stop or self.paused:return False
            if self.origin is None:self.origin=time.monotonic()
            self.latest=image;self.condition.notify();return True

    def offer_audio(self,raw,rate=16000,channels=2):
        if not self.audio or rate!=16000 or channels!=2 or not isinstance(raw,bytes) or len(raw)!=6400:return
        with self.condition:
            if self._stop or self.paused or self.origin is None:return
            if len(self.audio_queue)>=100 or (self.audio_next_time is not None and self.audio_next_time>self.elapsed+2):
                self.warning='A gravação foi encerrada porque o áudio acumulou atraso.';self._stop=True
            else:
                now=time.monotonic();start=max(0.,self.elapsed-.1)
                if self.audio_next_time is not None:
                    if self.audio_last_wall is not None and now-self.audio_last_wall<.5 and abs(self.audio_next_time-start)<=.15:
                        start=self.audio_next_time
                    else:
                        # A burst or a stall must not move all later audio away
                        # from the received video clock. Discard only buffered,
                        # unencoded audio when reanchoring; encoded PTS stay continuous.
                        self.audio_epoch+=1;self.audio_queue.clear()
                self.audio_queue.append((self.audio_epoch,round(start*16000),raw));self.audio_next_time=start+.1;self.audio_last_wall=now;self.audio_received_samples+=1600
            self.condition.notify()

    def pause(self,paused):
        with self.condition:
            if self._stop:return
            if paused and not self.paused:self.pause_start=time.monotonic()
            elif not paused and self.paused:
                self.paused_total+=time.monotonic()-self.pause_start;self.pause_start=None
                self.audio_epoch+=1;self.audio_queue.clear();self.audio_next_time=None;self.audio_last_wall=None
            self.condition.notify()

    def stop(self):
        with self.condition:self._stop=True;self.condition.notify()

    def wait(self,timeout=10):
        if self.thread and self.thread is not threading.current_thread():self.thread.join(timeout)
        return self.finished.is_set()

    def _frame(self,image):
        if image.mode!='RGB':image=image.convert('RGB')
        if self.size is None:
            ratio=min(1.,self.max_width/image.width,1440/image.height)
            self.size=(max(2,int(image.width*ratio)//2*2),max(2,int(image.height*ratio)//2*2))
        if image.size!=self.size:
            fitted=ImageOps.contain(image,self.size,Image.Resampling.LANCZOS)
            canvas=Image.new('RGB',self.size);canvas.paste(fitted,((self.size[0]-fitted.width)//2,(self.size[1]-fitted.height)//2));image=canvas
        return image

    def _run(self):
        temporary=self.path.with_name('.desk-recording-'+self.id+'.part');container=None
        success=False;error='';duration=0.;last_pts=-1;audio_end=0;pending_audio=deque();pending_epoch=0
        try:
            import av,numpy as np
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with self.condition:
                while self.latest is None and not self._stop:self.condition.wait(.2)
                if self.latest is None:raise ValueError('Nenhuma imagem recebida para gravar.')
                initial=self._frame(self.latest)
            with temporary.open('xb') as output:
                container=av.open(output,mode='w',format='mp4',options={'movflags':'+faststart'})
                video=container.add_stream('libx264',rate=self.fps);video.width,video.height=self.size;video.pix_fmt='yuv420p'
                video.options={'preset':'ultrafast','crf':'20','tune':'zerolatency'};video.codec_context.thread_count=2
                audio=container.add_stream('aac',rate=16000) if self.audio else None
                if audio:audio.layout='stereo';audio.codec_context.format='fltp'
                resampler=av.AudioResampler(format='fltp',layout='stereo',rate=16000) if audio else None
                while True:
                    with self.condition:
                        stopping=self._stop;elapsed=self.elapsed;paused=self.paused
                        audio_blocks=list(self.audio_queue);self.audio_queue.clear();image=self.latest;epoch=self.audio_epoch
                        slot=int(elapsed*self.fps)
                        target_audio=round(max(0.,elapsed if stopping or paused else elapsed-.2)*16000)
                        audio_due=audio is not None and audio_end<target_audio
                        if not stopping and (paused or slot<=last_pts) and not audio_blocks and not audio_due and epoch==pending_epoch:
                            self.condition.wait(.05 if paused else max(.001,(last_pts+1)/self.fps-elapsed));continue
                    if epoch!=pending_epoch:pending_audio.clear();pending_epoch=epoch
                    pending_audio.extend((start,raw) for generation,start,raw in audio_blocks if generation==pending_epoch)
                    while audio is not None and audio_end<target_audio:
                        while pending_audio and pending_audio[0][0]+len(pending_audio[0][1])//4<=audio_end:pending_audio.popleft()
                        count=min(1600,target_audio-audio_end)
                        if pending_audio and pending_audio[0][0]<=audio_end:
                            start,raw=pending_audio[0];offset=audio_end-start;count=min(count,len(raw)//4-offset);raw=raw[offset*4:(offset+count)*4]
                        else:
                            if pending_audio:count=min(count,pending_audio[0][0]-audio_end)
                            raw=b'\0'*(count*4)
                        if count<=0:break
                        frame=av.AudioFrame.from_ndarray(np.frombuffer(raw,dtype='<i2').reshape(1,-1),format='s16',layout='stereo')
                        frame.sample_rate=16000;frame.time_base=Fraction(1,16000);frame.pts=audio_end;audio_end+=frame.samples
                        for converted in resampler.resample(frame):
                            for packet in audio.encode(converted):container.mux(packet)
                        self.audio_samples+=frame.samples
                    if image is not None and not paused and slot>last_pts:
                        frame=av.VideoFrame.from_image(self._frame(image));frame.pts=slot;frame.time_base=Fraction(1,self.fps)
                        for packet in video.encode(frame):container.mux(packet)
                        self.frames+=1;last_pts=slot
                    if stopping:break
                for packet in video.encode():container.mux(packet)
                if audio:
                    for converted in resampler.resample(None):
                        for packet in audio.encode(converted):container.mux(packet)
                    for packet in audio.encode():container.mux(packet)
                container.close();container=None;output.flush();os.fsync(output.fileno())
            if not self.frames:raise ValueError('A gravação não recebeu imagens antes de ser encerrada.')
            if self.audio and not self.audio_received_samples and not self.warning:self.warning='O vídeo foi salvo sem áudio recebido. Confira a fonte de áudio e a permissão da sessão.'
            temporary.replace(self.path);success=True;duration=max(self.elapsed,(last_pts+1)/self.fps,audio_end/16000)
        except Exception as ex:error=str(ex)[:240]
        finally:
            if container:
                try:container.close()
                except Exception:pass
            temporary.unlink(missing_ok=True)
            with self.condition:self._stop=True;self.latest=None;self.audio_queue.clear()
            self.result=dict(id=self.id,success=success,path=str(self.path) if success else '',error=error,warning=self.warning,
                             frames=self.frames,audio_samples=self.audio_samples,audio_received_samples=self.audio_received_samples,duration=round(duration,3),size=self.size)
            self.finished.set()
            try:self.event('recording_done',self.result)
            except RuntimeError:pass


class LocalRecordingFeed:
    """Screen and optional WASAPI loopback; never starts a microphone."""
    def __init__(self,recorder,monitor=1):self.recorder=recorder;self.monitor=monitor;self.closed=threading.Event();self.threads=[]
    def start(self):
        for target in ([self._screen,self._audio] if self.recorder.audio else [self._screen]):
            thread=threading.Thread(target=target,name='Desk local recording',daemon=True);self.threads.append(thread);thread.start()
        return self
    def stop(self):self.closed.set()
    def _screen(self):
        try:
            import mss
            with mss.MSS() as source:
                if not 0<=self.monitor<len(source.monitors):raise ValueError('Monitor de gravação indisponível.')
                while not self.closed.is_set() and not self.recorder.finished.is_set():
                    start=time.monotonic()
                    if not self.recorder.paused:
                        shot=source.grab(source.monitors[self.monitor]);image=Image.frombytes('RGB',shot.size,shot.bgra,'raw','BGRX')
                        if image.width>self.recorder.max_width or image.height>1440:image.thumbnail((self.recorder.max_width,1440),Image.Resampling.LANCZOS)
                        self.recorder.offer(image)
                    self.closed.wait(max(.001,1/self.recorder.fps-(time.monotonic()-start)))
        except Exception as ex:self.recorder.warning='Captura local interrompida: '+str(ex)[:160];self.recorder.stop()
    def _audio(self):
        try:
            import soundcard as sc,numpy as np
            speaker=sc.default_speaker()
            if speaker is None:raise RuntimeError('Nenhuma saída de áudio encontrada.')
            loopback=sc.get_microphone(speaker.id,include_loopback=True)
            if not loopback or not loopback.isloopback:raise RuntimeError('Loopback indisponível.')
            while not self.closed.is_set() and not self.recorder.finished.is_set():
                if self.recorder.paused:self.closed.wait(.05);continue
                with loopback.recorder(samplerate=16000,channels=2,blocksize=1600) as source:
                    while not self.closed.is_set() and not self.recorder.finished.is_set() and not self.recorder.paused:
                        raw=(np.clip(source.record(numframes=1600),-1,1)*32767).astype('<i2').tobytes();self.recorder.offer_audio(raw)
        except Exception as ex:self.recorder.warning='Vídeo gravado sem áudio do sistema: '+str(ex)[:160]
