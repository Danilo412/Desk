"""Synthetic advanced-feature checks; never reboots, prints physically or captures the desktop."""
from pathlib import Path
from contextlib import nullcontext
from collections import deque
import tempfile,time
from PIL import Image

def advanced_test(relay=None):
    from .session import HostService,join
    from .identity import IdentityStore
    from .recording import VideoRecorder
    from .folders import extract_folder
    from .printing import document_pages,render_page,paint_document
    from . import remote_features
    from PySide6.QtWidgets import QApplication
    from PySide6.QtPrintSupport import QPrinter
    import av
    application=QApplication.instance() or QApplication([])
    host=viewer=recorder=None;checks={};phase='setup';events=deque(maxlen=256);host_events=deque(maxlen=256);latest=[None];approvals=[]
    original_info=remote_features.system_information
    remote_features.system_information=lambda monitors:{'Computador':'Laboratório sintético','Sistema':'Windows de teste','Memória RAM':'16 GB'}
    class Synthetic:
        def __init__(self):self.inputs=[];self.rect=dict(left=0,top=0,width=2560,height=1440)
        def monitors(self):return [dict(self.rect)]*2
        def capture_source(self):return nullcontext()
        def capture(self,source,index,width):return Image.new('RGB',(width,width*9//16),(35,110,170))
        def input(self,data):self.inputs.append(data)
        def release(self):pass
    def wait(predicate,seconds=60):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if predicate():return
            application.processEvents();time.sleep(.015)
        raise TimeoutError('Diagnóstico avançado não concluiu a etapa.')
    def viewer_event(name,data):
        if name=='frame':
            latest[0]=data
            if recorder:recorder.offer(data)
        else:events.append((name,data))
    try:
        with tempfile.TemporaryDirectory(prefix='desk-advanced-test-') as directory:
            base=Path(directory);received=base/'recebidos';received.mkdir();desktop=Synthetic()
            document=base/'documento.pdf';Image.new('RGB',(240,120),'#426890').save(document,'PDF')
            folder=base/'pasta';(folder/'sub').mkdir(parents=True);(folder/'sub/arquivo.txt').write_text('pasta conferida',encoding='utf-8');(folder/'vazia').mkdir()
            def request(kind,data,timeout):
                if kind=='consent':approvals.append('consent');return True
                if kind=='save_file':return str(received/Path(data['name']).name)
                if kind=='advanced_action':
                    operation=data['operation'];approvals.append(operation)
                    return str(document) if operation=='print' else operation!='restart'
                return None
            host=HostService(desktop,lambda k,d:host_events.append((k,d)),request,dict(control=True,clipboard=False,audio=False),identity=IdentityStore(base/'host'),relay=relay)
            token=host.start('unused' if relay else '127.0.0.1',**({} if relay else dict(bind_address='127.0.0.1')))
            if relay:wait(lambda:any(k=='relay_ready' for k,d in host_events))
            viewer=join(token,viewer_event,request,identity=IdentityStore(base/'viewer'));viewer.start()
            phase='capabilities';wait(lambda:latest[0] is not None and len(viewer.remote_capabilities)==4)
            assert viewer.channel.sock.version()=='TLSv1.3';checks['capabilities_and_synthetic_screen_tls13']=True
            if relay:
                for peer in (viewer,host.peer):
                    pairs=peer.channel.sock.outer.candidate_types;assert pairs and all(tuple(pair)==('relay','relay') for pair in pairs)
                checks['public_turn_forced_both_endpoints']=True
            phase='record1080';recorder=VideoRecorder(base/'1080.mp4').start();recorder.offer(latest[0]);time.sleep(.35);recorder.stop();assert recorder.wait() and recorder.result['success'];recorder=None
            with av.open(str(base/'1080.mp4')) as source:
                frame=next(source.decode(video=0));assert (frame.width,frame.height)==(1920,1080)
            checks['recording1080_mp4_decoded']=True
            phase='record1440';viewer.send(dict(type='view',monitor=1,mode='deflate',width=2560,fps=15));wait(lambda:latest[0].size==(2560,1440))
            recorder=VideoRecorder(base/'1440.mp4').start();recorder.offer(latest[0]);time.sleep(.4);recorder.stop();assert recorder.wait() and recorder.result['success'];recorder=None
            with av.open(str(base/'1440.mp4')) as source:
                frame=next(source.decode(video=0));assert (frame.width,frame.height)==(2560,1440)
            checks['recording1440_mp4_decoded']=True
            phase='audio48';import numpy as np,os
            from .audio_codec import OpusEncoder,OpusDecoder
            from .audio_transport import AudioCipher
            encoder=OpusEncoder();decoder=OpusDecoder();key=os.urandom(32);prefix=os.urandom(4)
            sender=AudioCipher(key,prefix);receiver=AudioCipher(key,prefix);audio_samples=[]
            recorder=VideoRecorder(base/'audio48.mp4',audio=True).start();recorder.offer(Image.new('RGB',(64,36),'navy'))
            for i in range(20):
                t=(np.arange(960)+i*960)/48000;input_audio=np.column_stack((.25*np.sin(2*np.pi*12000*t),.25*np.sin(2*np.pi*3500*t)))
                packet=sender.seal(encoder.encode(input_audio));decoded=receiver.open(packet);assert decoded is not None and receiver.open(packet) is None
                raw=decoder.decode(decoded);audio_samples.append(np.frombuffer(raw,'<i2').reshape(-1,2));recorder.offer_audio(raw,48000,2);time.sleep(.02)
            recorder.stop();assert recorder.wait() and recorder.result['success'];recorder=None
            signal=np.concatenate(audio_samples)[2000:,0];peak=np.fft.rfftfreq(len(signal),1/48000)[np.argmax(np.abs(np.fft.rfft(signal)))]
            assert abs(peak-12000)<15;checks['opus48_stereo_and_authenticated_side_packets']=True
            with av.open(str(base/'audio48.mp4')) as source:
                assert source.streams.audio[0].rate==48000 and next(source.decode(audio=0)).layout.nb_channels==2
            checks['recording48_audio_mp4']=True
            phase='chat';viewer.send(dict(type='chat',text='conversa para exportação'));wait(lambda:any(k=='chat' and d['text']=='conversa para exportação' for k,d in host_events));checks['chat_over_connection']=True
            def operation(name):
                time.sleep(1.05);request_id=viewer.features.request(name)
                wait(lambda:any(k=='advanced_result' and d['id']==request_id for k,d in events))
                return next(d for k,d in events if k=='advanced_result' and d['id']==request_id)
            phase='information';result=operation('system_info');assert result['status']=='accepted' and result['values']['Computador']=='Laboratório sintético';checks['approved_remote_information']=True
            phase='restart_declined';result=operation('restart');assert result['status']=='declined';checks['restart_decline_no_system_action']=True
            phase='annotations';assert operation('whiteboard')['status']=='accepted'
            viewer.features.send_stroke(dict(shape='arrow',color='#ef443b',width=3,points=[[.1,.2],[.8,.7]]));wait(lambda:any(k=='annotation' for k,d in host_events))
            assert not desktop.inputs;checks['approved_annotations_without_input_injection']=True
            host.peer.set_permissions(dict(control=False));wait(lambda:not viewer.features.viewer_whiteboard);checks['annotation_permission_revocation']=True
            phase='folder';viewer.send_folder(folder);wait(lambda:(received/'pasta.zip').exists())
            extracted=extract_folder(received/'pasta.zip',received)
            assert (extracted/'sub/arquivo.txt').read_text(encoding='utf-8')=='pasta conferida' and (extracted/'vazia').is_dir();checks['folder_transfer_sha256_and_extraction']=True
            phase='print_document';assert operation('print')['status']=='accepted';wait(lambda:(received/document.name).exists())
            assert (received/document.name).read_bytes()==document.read_bytes() and document_pages(received/document.name)==1
            printer=QPrinter();printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat);printer.setOutputFileName(str(base/'impressao.pdf'))
            assert paint_document(received/document.name,printer)==1 and not render_page(base/'impressao.pdf').isNull();checks['remote_pdf_transfer_and_local_pdf_print']=True
            assert approvals==['consent','system_info','restart','whiteboard','print'];checks['explicit_operation_approvals']=True
        return dict(passed=True,checks=checks,scope='Synthetic two peers on one PC; MP4s decoded at 1080p/1440p, local PDF print output. No real desktop/audio capture, physical printing or real reboot.',credentials_output=False)
    except Exception as ex:return dict(passed=False,checks=checks,phase=phase,error_type=type(ex).__name__,credentials_output=False)
    finally:
        if recorder:recorder.stop();recorder.wait()
        if viewer:viewer.close();viewer.wait_for_workers()
        if host:host.stop()
        remote_features.system_information=original_info
