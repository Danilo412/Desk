// Desk privileged screen broker. No listener on TCP/UDP, no shell/file RPC,
// no password API and no input logging. Trust is an administrative publisher
// pin or an explicit fixed-version pin; neither changes Windows app control.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Security.Principal;
using System.ServiceProcess;
using System.Text;
using System.Threading;
using Microsoft.Win32.SafeHandles;
using Microsoft.Win32;
[assembly:AssemblyTitle("Desk - screen broker")]
[assembly:AssemblyProduct("Desk")]
[assembly:AssemblyVersion("0.13.1.0")]
[assembly:AssemblyFileVersion("0.13.1.0")]
[assembly:DefaultDllImportSearchPaths(DllImportSearchPath.System32)]

namespace DeskHost {
    static class Wire {
        public const int MaxRequest=512, MaxReply=32*1024*1024;
        public static byte[] Read(Stream stream,int maximum) {
            byte[] header=Exact(stream,4);uint size=BitConverter.ToUInt32(header,0);
            if(size<1 || size>maximum)throw new InvalidDataException("Packet size");
            return Exact(stream,(int)size);
        }
        static byte[] Exact(Stream stream,int count) {
            byte[] data=new byte[count];int offset=0;
            while(offset<count){int n=stream.Read(data,offset,count-offset);if(n==0)throw new EndOfStreamException();offset+=n;}
            return data;
        }
        public static void Write(Stream stream,byte[] data,int maximum) {
            if(data.Length<1 || data.Length>maximum)throw new InvalidDataException("Packet size");
            byte[] size=BitConverter.GetBytes(data.Length);stream.Write(size,0,4);stream.Write(data,0,data.Length);stream.Flush();
        }
        public static byte[] Result(Action<BinaryWriter> write) {
            using(MemoryStream m=new MemoryStream())using(BinaryWriter w=new BinaryWriter(m)){w.Write((byte)0);write(w);return m.ToArray();}
        }
        public static void Validate(byte[] p) {
            if(p.Length<1 || p.Length>MaxRequest)throw new InvalidDataException("Packet size");
            byte op=p[0];
            if(op==1 || op==2 || op==5 || op==6){if(p.Length!=1)throw new InvalidDataException("Packet size");return;}
            if(op==3){if(p.Length!=10)throw new InvalidDataException("Capture request");int monitor=BitConverter.ToInt32(p,1);int width=BitConverter.ToUInt16(p,5),height=BitConverter.ToUInt16(p,7);if(monitor<0 || monitor>32 || width<1 || width>3840 || height<1 || height>2160 || p[9]!=1)throw new InvalidDataException("Capture limits");return;}
            if(op!=4 || p.Length<2)throw new InvalidDataException("Operation");
            int kind=p[1];int length=kind==1?18:kind==2?5:kind==3?20:kind==4?6:kind==5?2:0;
            if(length==0 || p.Length!=length)throw new InvalidDataException("Input size");
            if(kind==1 || kind==3){int at=kind==1?2:4;double x=BitConverter.ToDouble(p,at),y=BitConverter.ToDouble(p,at+8);if(Double.IsNaN(x)||Double.IsInfinity(x)||Double.IsNaN(y)||Double.IsInfinity(y)||x<0||x>1||y<0||y>1)throw new InvalidDataException("Coordinates");}
            if(kind==2 && (BitConverter.ToUInt16(p,2)<1 || BitConverter.ToUInt16(p,2)>254 || p[4]>1))throw new InvalidDataException("Key");
            if(kind==3 && (p[2]>4 || p[3]>1))throw new InvalidDataException("Button");
            if(kind==4 && (BitConverter.ToInt32(p,2)<-1200 || BitConverter.ToInt32(p,2)>1200))throw new InvalidDataException("Wheel");
        }
    }

    static class Trust {
        public static string Exe { get { return Path.GetFullPath(Assembly.GetExecutingAssembly().Location); } }
        public static string Hash(string path){using(SHA256 h=SHA256.Create())using(FileStream s=File.Open(path,FileMode.Open,FileAccess.Read,FileShare.Read)){return BitConverter.ToString(h.ComputeHash(s)).Replace("-","").ToLowerInvariant();}}
        public static bool IsSystem {get{return WindowsIdentity.GetCurrent().User.Value=="S-1-5-18";}}
        public static void Admin(){if(!new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator))throw new UnauthorizedAccessException("Administrator required");}
        public static void SafeRoot(){string expected=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),"DeskHost");if(!String.Equals(Path.GetDirectoryName(Exe),expected,StringComparison.OrdinalIgnoreCase) || (File.GetAttributes(expected)&FileAttributes.ReparsePoint)!=0 || (File.GetAttributes(Exe)&FileAttributes.ReparsePoint)!=0)throw new UnauthorizedAccessException("Protected install location required");}
        public static string SignedPublisher(string file) {
            Guid action=new Guid("00AAC56B-CD44-11d0-8CC2-00C04FC295EE");
            Native.WINTRUST_FILE_INFO info=new Native.WINTRUST_FILE_INFO();info.cbStruct=(uint)Marshal.SizeOf(info);info.pcwszFilePath=file;
            IntPtr pointer=Marshal.AllocHGlobal(Marshal.SizeOf(info));Marshal.StructureToPtr(info,pointer,false);
            Native.WINTRUST_DATA data=new Native.WINTRUST_DATA();data.cbStruct=(uint)Marshal.SizeOf(data);data.dwUIChoice=2;data.fdwRevocationChecks=1;data.dwUnionChoice=1;data.pFile=pointer;data.dwStateAction=1;data.dwProvFlags=0x80;
            int result;
            try {result=Native.WinVerifyTrust(new IntPtr(-1),ref action,ref data);}
            finally {data.dwStateAction=2;Native.WinVerifyTrust(new IntPtr(-1),ref action,ref data);Marshal.DestroyStructure(pointer,typeof(Native.WINTRUST_FILE_INFO));Marshal.FreeHGlobal(pointer);}
            if(result!=0)throw new UnauthorizedAccessException("Trusted Authenticode signature required");
            using(X509Certificate2 cert=new X509Certificate2(X509Certificate.CreateFromSignedFile(file))){return cert.Thumbprint.ToUpperInvariant();}
        }
        public static void LockAcl(string path,bool directory) {
            FileSystemSecurity acl=directory?(FileSystemSecurity)new DirectorySecurity():new FileSecurity();
            acl.SetAccessRuleProtection(true,false);SecurityIdentifier admins=new SecurityIdentifier("S-1-5-32-544"),system=new SecurityIdentifier("S-1-5-18"),users=new SecurityIdentifier("S-1-5-32-545");acl.SetOwner(admins);
            InheritanceFlags flags=directory?InheritanceFlags.ContainerInherit|InheritanceFlags.ObjectInherit:InheritanceFlags.None;
            acl.AddAccessRule(new FileSystemAccessRule(admins,FileSystemRights.FullControl,flags,PropagationFlags.None,AccessControlType.Allow));
            acl.AddAccessRule(new FileSystemAccessRule(system,FileSystemRights.FullControl,flags,PropagationFlags.None,AccessControlType.Allow));
            acl.AddAccessRule(new FileSystemAccessRule(users,FileSystemRights.ReadAndExecute,flags,PropagationFlags.None,AccessControlType.Allow));
            if(directory)Directory.SetAccessControl(path,(DirectorySecurity)acl);else File.SetAccessControl(path,(FileSecurity)acl);
        }
        public static void CheckAcl(string path,bool directory) {
            if((File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0)throw new UnauthorizedAccessException("Reparse point");
            FileSystemSecurity acl=directory?(FileSystemSecurity)Directory.GetAccessControl(path):File.GetAccessControl(path);
            string owner=((SecurityIdentifier)acl.GetOwner(typeof(SecurityIdentifier))).Value;
            if(owner!="S-1-5-18" && owner!="S-1-5-32-544")throw new UnauthorizedAccessException("Unprotected owner");
            FileSystemRights write=FileSystemRights.Write|FileSystemRights.Delete|FileSystemRights.ChangePermissions|FileSystemRights.TakeOwnership|FileSystemRights.DeleteSubdirectoriesAndFiles;
            foreach(FileSystemAccessRule rule in acl.GetAccessRules(true,true,typeof(SecurityIdentifier))){string sid=((SecurityIdentifier)rule.IdentityReference).Value;if(rule.AccessControlType==AccessControlType.Allow && (rule.FileSystemRights&write)!=0 && sid!="S-1-5-18" && sid!="S-1-5-32-544")throw new UnauthorizedAccessException("Unprotected write access");}
        }
    }

    [DataContract] sealed class Config {
        [DataMember] public string OwnerSid;
        [DataMember] public string ClientPath;
        [DataMember] public string ClientHash;
        [DataMember] public string Publisher;
        [DataMember] public string TrustMode;
        [DataMember] public string ServiceHash;
        public bool FixedVersion {get{return TrustMode=="fixed";}}
        static string FilePath {get{return Path.Combine(Path.GetDirectoryName(Trust.Exe),"service.json");}}
        public string Pipe {get{return "DeskHost."+OwnerSid;}}
        public static Config Load(){Trust.SafeRoot();Trust.CheckAcl(Path.GetDirectoryName(Trust.Exe),true);Trust.CheckAcl(Trust.Exe,false);Trust.CheckAcl(FilePath,false);using(FileStream s=File.OpenRead(FilePath)){Config c=(Config)new DataContractJsonSerializer(typeof(Config)).ReadObject(s);c.Validate();return c;}}
        public void Validate(){SecurityIdentifier sid=new SecurityIdentifier(OwnerSid);if(!sid.IsAccountSid() || ClientHash==null || ClientHash.Length!=64 || ServiceHash==null || ServiceHash.Length!=64 || !Path.IsPathRooted(ClientPath) || !String.Equals(Path.GetFileName(ClientPath),"Desk.exe",StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("Configuration");ClientPath=Path.GetFullPath(ClientPath);if(Trust.Hash(Trust.Exe)!=ServiceHash)throw new UnauthorizedAccessException("Service version");if(TrustMode!="fixed" && TrustMode!="publisher")throw new InvalidDataException("Trust mode");if(!FixedVersion && !String.Equals(Trust.SignedPublisher(Trust.Exe),Publisher,StringComparison.OrdinalIgnoreCase))throw new UnauthorizedAccessException("Publisher");}
        public static void Install(string sid,string client,string expectedHash=null){
            Trust.Admin();Trust.SafeRoot();bool fixedVersion=expectedHash!=null;client=Path.GetFullPath(client);string publisher="";
            if(fixedVersion){if(expectedHash.Length!=64 || Trust.Hash(client)!=expectedHash)throw new UnauthorizedAccessException("Explicit client version required");}
            else{publisher=Trust.SignedPublisher(Trust.Exe);if(!String.Equals(Trust.SignedPublisher(client),publisher,StringComparison.OrdinalIgnoreCase))throw new UnauthorizedAccessException("Matching trusted publisher required");}
            Config c=new Config();c.OwnerSid=new SecurityIdentifier(sid).Value;c.ClientPath=client;c.ClientHash=Trust.Hash(client);c.Publisher=publisher;c.TrustMode=fixedVersion?"fixed":"publisher";c.ServiceHash=Trust.Hash(Trust.Exe);c.Validate();
            IntPtr scm=Native.OpenSCManager(null,null,3);if(scm==IntPtr.Zero)throw new System.ComponentModel.Win32Exception();
            try {IntPtr existing=Native.OpenService(scm,"DeskScreenBroker",0x10000|0x20|0x10|0x1);if(existing!=IntPtr.Zero){Native.CloseServiceHandle(existing);throw new InvalidOperationException("Remove existing service before replacing its protected files");}
                if(Marshal.GetLastWin32Error()!=1060)throw new System.ComponentModel.Win32Exception();
                Trust.LockAcl(Path.GetDirectoryName(Trust.Exe),true);Trust.LockAcl(Trust.Exe,false);
                using(FileStream s=File.Create(FilePath))new DataContractJsonSerializer(typeof(Config)).WriteObject(s,c);Trust.LockAcl(FilePath,false);
                IntPtr service=Native.CreateService(scm,"DeskScreenBroker","Desk - tela de bloqueio",0xF01FF,0x10,2,1,"\""+Trust.Exe+"\" --service",null,IntPtr.Zero,null,null,null);
                if(service==IntPtr.Zero)throw new System.ComponentModel.Win32Exception();
                try {
                    using(RegistryKey key=Registry.LocalMachine.CreateSubKey(@"SOFTWARE\DeskHost")){
                        RegistrySecurity acl=new RegistrySecurity();SecurityIdentifier admins=new SecurityIdentifier("S-1-5-32-544"),system=new SecurityIdentifier("S-1-5-18");acl.SetOwner(admins);acl.SetAccessRuleProtection(true,false);
                        acl.AddAccessRule(new RegistryAccessRule(admins,RegistryRights.FullControl,InheritanceFlags.ContainerInherit,PropagationFlags.None,AccessControlType.Allow));
                        acl.AddAccessRule(new RegistryAccessRule(system,RegistryRights.FullControl,InheritanceFlags.ContainerInherit,PropagationFlags.None,AccessControlType.Allow));
                        acl.AddAccessRule(new RegistryAccessRule(new SecurityIdentifier("S-1-5-32-545"),RegistryRights.ReadKey,InheritanceFlags.ContainerInherit,PropagationFlags.None,AccessControlType.Allow));key.SetAccessControl(acl);
                        key.SetValue("ServiceHash",c.ServiceHash);key.SetValue("OwnerSid",c.OwnerSid);key.SetValue("ClientHash",c.ClientHash);key.SetValue("ClientPath",c.ClientPath);key.SetValue("TrustMode",c.TrustMode);
                    }
                    if(!Native.StartService(service,0,IntPtr.Zero))throw new System.ComponentModel.Win32Exception();
                    using(ServiceController controller=new ServiceController("DeskScreenBroker"))controller.WaitForStatus(ServiceControllerStatus.Running,TimeSpan.FromSeconds(15));
                }catch{Native.SERVICE_STATUS status;Native.ControlService(service,1,out status);Native.DeleteService(service);Registry.LocalMachine.DeleteSubKeyTree(@"SOFTWARE\DeskHost",false);throw;}finally{Native.CloseServiceHandle(service);}
            }finally{Native.CloseServiceHandle(scm);}
        }
        public static void Remove(){Trust.Admin();Load();IntPtr scm=Native.OpenSCManager(null,null,1);if(scm==IntPtr.Zero)throw new System.ComponentModel.Win32Exception();try{IntPtr service=Native.OpenService(scm,"DeskScreenBroker",0x10000|0x20|0x4);if(service==IntPtr.Zero){if(Marshal.GetLastWin32Error()!=1060)throw new System.ComponentModel.Win32Exception();}else{try{Native.SERVICE_STATUS status;Native.ControlService(service,1,out status);using(ServiceController controller=new ServiceController("DeskScreenBroker"))controller.WaitForStatus(ServiceControllerStatus.Stopped,TimeSpan.FromSeconds(15));if(!Native.DeleteService(service))throw new System.ComponentModel.Win32Exception();}finally{Native.CloseServiceHandle(service);}}Registry.LocalMachine.DeleteSubKeyTree(@"SOFTWARE\DeskHost",false);}finally{Native.CloseServiceHandle(scm);}}
    }

    sealed class AgentProcess:IDisposable {
        AnonymousPipeServerStream toAgent,fromAgent;IntPtr process=IntPtr.Zero,job=IntPtr.Zero,threadHandle=IntPtr.Zero;
        public AgentProcess(uint session) {
            if(!Trust.IsSystem || session==0 || session==UInt32.MaxValue)throw new UnauthorizedAccessException("Interactive console session required");
            IntPtr token=IntPtr.Zero,primary=IntPtr.Zero,list=IntPtr.Zero,handles=IntPtr.Zero;
            try {
                toAgent=new AnonymousPipeServerStream(PipeDirection.Out,HandleInheritability.Inheritable);fromAgent=new AnonymousPipeServerStream(PipeDirection.In,HandleInheritability.Inheritable);
                if(!Native.OpenProcessToken(Native.GetCurrentProcess(),0xB, out token) || !Native.DuplicateTokenEx(token,0xF01FF,IntPtr.Zero,2,1,out primary))throw new System.ComponentModel.Win32Exception();
                if(!Native.SetTokenInformation(primary,12,ref session,4))throw new System.ComponentModel.Win32Exception();
                IntPtr bytes=IntPtr.Zero;Native.InitializeProcThreadAttributeList(IntPtr.Zero,1,0,ref bytes);list=Marshal.AllocHGlobal(bytes);if(!Native.InitializeProcThreadAttributeList(list,1,0,ref bytes))throw new System.ComponentModel.Win32Exception();
                handles=Marshal.AllocHGlobal(IntPtr.Size*2);Marshal.WriteIntPtr(handles,0,new IntPtr(Int64.Parse(toAgent.GetClientHandleAsString())));Marshal.WriteIntPtr(handles,IntPtr.Size,new IntPtr(Int64.Parse(fromAgent.GetClientHandleAsString())));
                if(!Native.UpdateProcThreadAttribute(list,0,new IntPtr(0x20002),handles,new IntPtr(IntPtr.Size*2),IntPtr.Zero,IntPtr.Zero))throw new System.ComponentModel.Win32Exception();
                Native.STARTUPINFOEX start=new Native.STARTUPINFOEX();start.StartupInfo.cb=Marshal.SizeOf(start);start.StartupInfo.lpDesktop="winsta0\\default";start.lpAttributeList=list;
                string command="\""+Trust.Exe+"\" --agent "+toAgent.GetClientHandleAsString()+" "+fromAgent.GetClientHandleAsString()+" "+Process.GetCurrentProcess().Id+" "+session;
                Native.PROCESS_INFORMATION pi;
                if(!Native.CreateProcessAsUser(primary,Trust.Exe,new StringBuilder(command),IntPtr.Zero,IntPtr.Zero,true,0x08080004,IntPtr.Zero,Path.GetDirectoryName(Trust.Exe),ref start,out pi))throw new System.ComponentModel.Win32Exception();
                process=pi.hProcess;threadHandle=pi.hThread;job=Native.CreateJobObject(IntPtr.Zero,null);if(job==IntPtr.Zero)throw new System.ComponentModel.Win32Exception();
                Native.JOB_LIMIT limit=new Native.JOB_LIMIT();limit.Basic.LimitFlags=0x2000;
                if(!Native.SetInformationJobObject(job,9,ref limit,(uint)Marshal.SizeOf(limit)) || !Native.AssignProcessToJobObject(job,process))throw new System.ComponentModel.Win32Exception();
                if(Native.ResumeThread(threadHandle)==UInt32.MaxValue)throw new System.ComponentModel.Win32Exception();Native.CloseHandle(threadHandle);threadHandle=IntPtr.Zero;toAgent.DisposeLocalCopyOfClientHandle();fromAgent.DisposeLocalCopyOfClientHandle();
            }catch{Dispose();throw;}finally{if(list!=IntPtr.Zero){Native.DeleteProcThreadAttributeList(list);Marshal.FreeHGlobal(list);}if(handles!=IntPtr.Zero)Marshal.FreeHGlobal(handles);if(primary!=IntPtr.Zero)Native.CloseHandle(primary);if(token!=IntPtr.Zero)Native.CloseHandle(token);}
        }
        byte[] ReadBounded(AnonymousPipeServerStream stream,int count,Stopwatch timer,int timeout){byte[] data=new byte[count];int offset=0;while(offset<count){if(timer.ElapsedMilliseconds>timeout)throw new System.TimeoutException("Worker response");uint available;if(!Native.PeekNamedPipe(stream.SafePipeHandle,IntPtr.Zero,0,IntPtr.Zero,out available,IntPtr.Zero))throw new EndOfStreamException();if(available==0){Thread.Sleep(1);continue;}int read=stream.Read(data,offset,Math.Min(count-offset,(int)available));if(read==0)throw new EndOfStreamException();offset+=read;}return data;}
        public byte[] Call(byte[] p){Wire.Validate(p);AnonymousPipeServerStream output=toAgent,input=fromAgent;if(output==null||input==null)throw new ObjectDisposedException("Worker");Wire.Write(output,p,Wire.MaxRequest);Stopwatch timer=Stopwatch.StartNew();int timeout=p[0]==3?5000:2000;byte[] header=ReadBounded(input,4,timer,timeout);uint size=BitConverter.ToUInt32(header,0);if(size<1||size>Wire.MaxReply)throw new InvalidDataException("Worker response size");return ReadBounded(input,(int)size,timer,timeout);}
        public void Dispose(){AnonymousPipeServerStream output=Interlocked.Exchange(ref toAgent,null),input=Interlocked.Exchange(ref fromAgent,null);IntPtr child=Interlocked.Exchange(ref process,IntPtr.Zero),thread=Interlocked.Exchange(ref threadHandle,IntPtr.Zero),group=Interlocked.Exchange(ref job,IntPtr.Zero);if(output!=null)output.Dispose();if(input!=null)input.Dispose();if(child!=IntPtr.Zero){if(Native.WaitForSingleObject(child,500)!=0)Native.TerminateProcess(child,20);Native.CloseHandle(child);}if(thread!=IntPtr.Zero)Native.CloseHandle(thread);if(group!=IntPtr.Zero)Native.CloseHandle(group);}
    }

    sealed class Broker:ServiceBase {
        Config config;volatile bool stopping;Thread worker;NamedPipeServerStream client;AgentProcess agent;Timer lease;long lastSeen;
        public Broker(Config c){config=c;ServiceName="DeskScreenBroker";AutoLog=false;CanStop=true;}
        protected override void OnStart(string[] args){lastSeen=Environment.TickCount;worker=new Thread(Run);worker.IsBackground=true;worker.Start();lease=new Timer(delegate(object unused){if(client!=null && unchecked(Environment.TickCount-(int)Interlocked.Read(ref lastSeen))>30000){try{client.Dispose();}catch{}try{if(agent!=null)agent.Dispose();}catch{}}},null,1000,1000);}
        protected override void OnStop(){stopping=true;if(lease!=null)lease.Dispose();try{if(client!=null)client.Dispose();}catch{}try{if(agent!=null)agent.Dispose();}catch{}if(worker!=null)worker.Join(2000);}
        NamedPipeServerStream NewPipe(){
            IntPtr sd=IntPtr.Zero;uint length;
            if(!Native.ConvertStringSecurityDescriptorToSecurityDescriptor("D:P(A;;GA;;;SY)(A;;GRGW;;;"+config.OwnerSid+")",1,out sd,out length))throw new System.ComponentModel.Win32Exception();
            try{Native.SECURITY_ATTRIBUTES sa=new Native.SECURITY_ATTRIBUTES();sa.nLength=Marshal.SizeOf(sa);sa.lpSecurityDescriptor=sd;
                IntPtr handle=Native.CreateNamedPipe("\\\\.\\pipe\\"+config.Pipe,3|0x80000,8,1,32768,32768,5000,ref sa);
                if(handle==new IntPtr(-1))throw new System.ComponentModel.Win32Exception();
                return new NamedPipeServerStream(PipeDirection.InOut,false,false,new SafePipeHandle(handle,true));
            }finally{Native.LocalFree(sd);}
        }
        uint Authenticate(NamedPipeServerStream pipe){
            uint pid;if(!Native.GetNamedPipeClientProcessId(pipe.SafePipeHandle,out pid))throw new UnauthorizedAccessException("Client identity");
            IntPtr process=Native.OpenProcess(0x1000,false,pid);if(process==IntPtr.Zero)throw new UnauthorizedAccessException("Client process");
            try{StringBuilder image=new StringBuilder(32768);uint n=(uint)image.Capacity;if(!Native.QueryFullProcessImageName(process,0,image,ref n) || !String.Equals(Path.GetFullPath(image.ToString()),config.ClientPath,StringComparison.OrdinalIgnoreCase))throw new UnauthorizedAccessException("Client image");
                IntPtr token;if(!Native.OpenProcessToken(process,8,out token))throw new UnauthorizedAccessException("Client token");
                try{using(WindowsIdentity identity=new WindowsIdentity(token)){if(identity.User.Value!=config.OwnerSid)throw new UnauthorizedAccessException("Client user");}}finally{Native.CloseHandle(token);}
                uint session;if(!Native.ProcessIdToSessionId(pid,out session) || session!=Native.WTSGetActiveConsoleSessionId() || session==0)throw new UnauthorizedAccessException("Client session");
                // Publisher/path/user/session pins survive ordinary signed
                // GUI updates. A changed or unsigned publisher is rejected.
                if(config.FixedVersion?Trust.Hash(config.ClientPath)!=config.ClientHash:Trust.SignedPublisher(config.ClientPath)!=config.Publisher)throw new UnauthorizedAccessException("Client authorization");
                return session;
            }finally{Native.CloseHandle(process);}
        }
        void Run(){while(!stopping){try{using(NamedPipeServerStream pipe=NewPipe()){
                    client=pipe;Interlocked.Exchange(ref lastSeen,Environment.TickCount);pipe.WaitForConnection();if(stopping)return;
                    uint session=Authenticate(pipe);agent=new AgentProcess(session);
                    try{while(!stopping && pipe.IsConnected){byte[] request=Wire.Read(pipe,Wire.MaxRequest);Wire.Validate(request);if(session!=Native.WTSGetActiveConsoleSessionId())throw new UnauthorizedAccessException("Console changed");Interlocked.Exchange(ref lastSeen,Environment.TickCount);Wire.Write(pipe,agent.Call(request),Wire.MaxReply);}}
                    finally{agent.Dispose();agent=null;}
                }}catch{if(!stopping)Thread.Sleep(100);}finally{client=null;}}
        }
    }

    sealed class DesktopAgent:IDisposable {
        IntPtr desktop=IntPtr.Zero;string desktopName="";Native.RECT selected,virtualRect;bool captured;uint desktopGeneration;HashSet<ushort> keys=new HashSet<ushort>();HashSet<byte> buttons=new HashSet<byte>();
        public DesktopAgent(){Native.SetProcessDpiAwarenessContext(new IntPtr(-4));Native.SetThreadDpiAwarenessContext(new IntPtr(-4));Native.AdjustTokenPrivilegesDisable();}
        bool Attach(){
            IntPtr next=Native.OpenInputDesktop(0,false,0x1|0x2|0x40|0x80|0x100);if(next==IntPtr.Zero)return false;
            StringBuilder name=new StringBuilder(256);uint needed;
            if(!Native.GetUserObjectInformation(next,2,name,512,out needed)){Native.CloseDesktop(next);return false;}
            string value=name.ToString();if(value!="Default" && value!="Winlogon" && value!="Screen-saver" && value!="ScreenSaver"){Native.CloseDesktop(next);return false;}
            if(value==desktopName){Native.CloseDesktop(next);return true;}
            if(!Native.SetThreadDesktop(next)){Native.CloseDesktop(next);return false;}
            Release();
            IntPtr old=desktop;desktop=next;desktopName=value;captured=false;desktopGeneration++;if(old!=IntPtr.Zero)Native.CloseDesktop(old);return true;
        }
        List<Native.RECT> Monitors(){List<Native.RECT> monitors=new List<Native.RECT>();Native.RECT whole=new Native.RECT();whole.Left=Native.GetSystemMetrics(76);whole.Top=Native.GetSystemMetrics(77);whole.Right=whole.Left+Native.GetSystemMetrics(78);whole.Bottom=whole.Top+Native.GetSystemMetrics(79);monitors.Add(whole);Native.MonitorEnum callback=delegate(IntPtr monitor,IntPtr dc,ref Native.RECT rect,IntPtr unused){monitors.Add(rect);return true;};if(!Native.EnumDisplayMonitors(IntPtr.Zero,IntPtr.Zero,callback,IntPtr.Zero))throw new System.ComponentModel.Win32Exception();return monitors;}
        void Rect(BinaryWriter writer,Native.RECT rect){writer.Write(rect.Left);writer.Write(rect.Top);writer.Write(rect.Right-rect.Left);writer.Write(rect.Bottom-rect.Top);}
        public byte[] Handle(byte[] p){Wire.Validate(p);if(!Attach())return new byte[]{1};
            if(p[0]==1)return Wire.Result(delegate(BinaryWriter w){w.Write((byte)(desktopName=="Default"?0:1));});
            if(p[0]==6)return Wire.Result(delegate(BinaryWriter w){w.Write((byte)(desktopName=="Default"?0:1));w.Write((byte)(captured?1:0));w.Write(desktopGeneration);});
            if(p[0]==2){List<Native.RECT> ms=Monitors();return Wire.Result(delegate(BinaryWriter w){w.Write((byte)ms.Count);foreach(Native.RECT rect in ms)Rect(w,rect);});}
            if(p[0]==5){Release();return new byte[]{0};}
            if(p[0]==4){Input(p);return new byte[]{0};}
            return Capture(BitConverter.ToInt32(p,1),BitConverter.ToUInt16(p,5),BitConverter.ToUInt16(p,7));
        }
        byte[] Capture(int index,int maxWidth,int maxHeight){
            List<Native.RECT> ms=Monitors();if(index>=ms.Count)throw new InvalidDataException("Monitor");Native.RECT rect=ms[index];int width=rect.Right-rect.Left,height=rect.Bottom-rect.Top;
            if(width<1 || height<1 || width>32768 || height>32768)throw new InvalidDataException("Monitor limits");
            double factor=Math.Min(1,Math.Min((double)maxWidth/width,(double)maxHeight/height));int w=Math.Max(1,(int)(width*factor)),h=Math.Max(1,(int)(height*factor)),stride=(w*3+3)&~3;
            IntPtr screen=Native.GetDC(IntPtr.Zero),memory=IntPtr.Zero,bitmap=IntPtr.Zero,previous=IntPtr.Zero;
            try{if(screen==IntPtr.Zero)throw new System.ComponentModel.Win32Exception();memory=Native.CreateCompatibleDC(screen);bitmap=Native.CreateCompatibleBitmap(screen,w,h);if(memory==IntPtr.Zero||bitmap==IntPtr.Zero)throw new System.ComponentModel.Win32Exception();previous=Native.SelectObject(memory,bitmap);Native.SetStretchBltMode(memory,4);
                if(!Native.StretchBlt(memory,0,0,w,h,screen,rect.Left,rect.Top,width,height,0x40CC0020))throw new System.ComponentModel.Win32Exception();
                Native.SelectObject(memory,previous);previous=IntPtr.Zero;Native.BITMAPINFO info=new Native.BITMAPINFO();info.header.size=40;info.header.width=w;info.header.height=-h;info.header.planes=1;info.header.bits=24;
                byte[] pixels=new byte[stride*h];if(Native.GetDIBits(memory,bitmap,0,(uint)h,pixels,ref info,0)!=(uint)h)throw new System.ComponentModel.Win32Exception();
                selected=rect;virtualRect=ms[0];captured=true;
                return Wire.Result(delegate(BinaryWriter writer){Rect(writer,selected);Rect(writer,virtualRect);writer.Write((ushort)w);writer.Write((ushort)h);writer.Write(stride);writer.Write(pixels);});
            }finally{if(previous!=IntPtr.Zero)Native.SelectObject(memory,previous);if(bitmap!=IntPtr.Zero)Native.DeleteObject(bitmap);if(memory!=IntPtr.Zero)Native.DeleteDC(memory);if(screen!=IntPtr.Zero)Native.ReleaseDC(IntPtr.Zero,screen);}
        }
        void Emit(Native.INPUT input){if(Native.SendInput(1,new Native.INPUT[]{input},Marshal.SizeOf(typeof(Native.INPUT)))!=1)throw new System.ComponentModel.Win32Exception();}
        public static int[] Project(Native.RECT selected,Native.RECT virtualRect,double x,double y){double px=selected.Left+Math.Round(x*(selected.Right-selected.Left-1)),py=selected.Top+Math.Round(y*(selected.Bottom-selected.Top-1));int vw=virtualRect.Right-virtualRect.Left,vh=virtualRect.Bottom-virtualRect.Top;if(vw<2||vh<2)throw new InvalidDataException("Virtual desktop");return new int[]{(int)Math.Max(0,Math.Min(65535,Math.Round((px-virtualRect.Left)*65535/(vw-1)))),(int)Math.Max(0,Math.Min(65535,Math.Round((py-virtualRect.Top)*65535/(vh-1))))};}
        void Mouse(uint flags,uint data,double x,double y,bool position){Native.INPUT input=new Native.INPUT();input.type=0;input.value.mouse.flags=flags;input.value.mouse.data=data;
            if(position){if(!captured)throw new InvalidOperationException("Capture required before positional input");int[] point=Project(selected,virtualRect,x,y);input.value.mouse.x=point[0];input.value.mouse.y=point[1];input.value.mouse.flags|=0xE001;}
            Emit(input);
        }
        static uint[] Down={2,8,32,128,128},Up={4,16,64,256,256};
        void Key(ushort vk,bool down){Native.INPUT input=new Native.INPUT();input.type=1;input.value.key.vk=vk;input.value.key.flags=(uint)(down?0:2);if((vk>=0x21&&vk<=0x28)||vk==0x2D||vk==0x2E||vk==0x5B||vk==0x5C||vk==0x5D||vk==0x6F||vk==0xA3||vk==0xA5)input.value.key.flags|=1;Emit(input);}
        void Input(byte[] p){int kind=p[1];if(kind!=5 && !captured)throw new InvalidOperationException("Capture required before input");if(kind==1)Mouse(0,0,BitConverter.ToDouble(p,2),BitConverter.ToDouble(p,10),true);
            else if(kind==2){ushort vk=BitConverter.ToUInt16(p,2);bool down=p[4]==1;Key(vk,down);if(down)keys.Add(vk);else keys.Remove(vk);}
            else if(kind==3){byte b=p[2];bool down=p[3]==1;Mouse(down?Down[b]:Up[b],b==3?1U:b==4?2U:0U,BitConverter.ToDouble(p,4),BitConverter.ToDouble(p,12),true);if(down)buttons.Add(b);else buttons.Remove(b);}
            else if(kind==4)Mouse(0x800,unchecked((uint)BitConverter.ToInt32(p,2)),0,0,false);else Release();
        }
        void Release(){foreach(ushort vk in keys){try{Key(vk,false);}catch{}}foreach(byte b in buttons){try{Mouse(Up[b],b==3?1U:b==4?2U:0U,0,0,false);}catch{}}keys.Clear();buttons.Clear();}
        public void Dispose(){try{Attach();}catch{}Release();if(desktop!=IntPtr.Zero){Native.CloseDesktop(desktop);desktop=IntPtr.Zero;}}
        public static void Run(string readHandle,string writeHandle,uint parent,uint session){
            if(!Trust.IsSystem || Process.GetCurrentProcess().SessionId!=(int)session || session==0)throw new UnauthorizedAccessException("System agent required");
            using(Process owner=Process.GetProcessById((int)parent)){if(!String.Equals(owner.MainModule.FileName,Trust.Exe,StringComparison.OrdinalIgnoreCase))throw new UnauthorizedAccessException("Broker parent");}
            Config.Load();
            using(AnonymousPipeClientStream input=new AnonymousPipeClientStream(PipeDirection.In,readHandle))using(AnonymousPipeClientStream output=new AnonymousPipeClientStream(PipeDirection.Out,writeHandle))using(DesktopAgent desktop=new DesktopAgent()){
                while(true){byte[] p;try{p=Wire.Read(input,Wire.MaxRequest);}catch(EndOfStreamException){break;}byte[] reply;try{reply=desktop.Handle(p);}catch{reply=new byte[]{1};}Wire.Write(output,reply,Wire.MaxReply);}
            }
        }
    }

    static class Native {
        [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] public struct WINTRUST_FILE_INFO {public uint cbStruct;[MarshalAs(UnmanagedType.LPWStr)]public string pcwszFilePath;public IntPtr hFile,pgKnownSubject;}
        [StructLayout(LayoutKind.Sequential)] public struct WINTRUST_DATA {public uint cbStruct;public IntPtr pPolicyCallbackData,pSIPClientData;public uint dwUIChoice,fdwRevocationChecks,dwUnionChoice;public IntPtr pFile;public uint dwStateAction;public IntPtr hWVTStateData,pwszURLReference;public uint dwProvFlags,dwUIContext;}
        [DllImport("wintrust.dll",ExactSpelling=true,PreserveSig=true)] public static extern int WinVerifyTrust(IntPtr window,ref Guid action,ref WINTRUST_DATA data);
        [StructLayout(LayoutKind.Sequential)] public struct SECURITY_ATTRIBUTES {public int nLength;public IntPtr lpSecurityDescriptor;[MarshalAs(UnmanagedType.Bool)]public bool bInheritHandle;}
        [StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)] public struct STARTUPINFO {public int cb;public string lpReserved,lpDesktop,lpTitle;public uint x,y,width,height,xChars,yChars,fill,flags;public ushort show,reserved2;public IntPtr reservedBytes,inHandle,outHandle,errorHandle;}
        [StructLayout(LayoutKind.Sequential)] public struct STARTUPINFOEX {public STARTUPINFO StartupInfo;public IntPtr lpAttributeList;}
        [StructLayout(LayoutKind.Sequential)] public struct PROCESS_INFORMATION {public IntPtr hProcess,hThread;public uint pid,tid;}
        [StructLayout(LayoutKind.Sequential)] public struct JOB_BASIC {public long processTime,jobTime;public uint LimitFlags;public UIntPtr minWorking,maxWorking;public uint active;public UIntPtr affinity;public uint priority,scheduling;}
        [StructLayout(LayoutKind.Sequential)] public struct IO_COUNTERS {public ulong r,w,o,rb,wb,ob;}
        [StructLayout(LayoutKind.Sequential)] public struct JOB_LIMIT {public JOB_BASIC Basic;public IO_COUNTERS io;public UIntPtr processMemory,jobMemory,peakProcess,peakJob;}
        [StructLayout(LayoutKind.Sequential)] public struct SERVICE_STATUS {public uint type,state,accepted,error,specific,checkpoint,wait;}
        [StructLayout(LayoutKind.Sequential)] public struct RECT {public int Left,Top,Right,Bottom;}
        [StructLayout(LayoutKind.Sequential)] public struct BITMAPHEADER {public uint size;public int width,height;public ushort planes,bits;public uint compression,imageSize;public int xPels,yPels;public uint colors,important;}
        [StructLayout(LayoutKind.Sequential)] public struct BITMAPINFO {public BITMAPHEADER header;public uint color;}
        [StructLayout(LayoutKind.Sequential)] public struct MOUSE {public int x,y;public uint data,flags,time;public UIntPtr extra;}
        [StructLayout(LayoutKind.Sequential)] public struct KEY {public ushort vk,scan;public uint flags,time;public UIntPtr extra;}
        [StructLayout(LayoutKind.Explicit)] public struct INPUT_UNION {[FieldOffset(0)]public MOUSE mouse;[FieldOffset(0)]public KEY key;}
        [StructLayout(LayoutKind.Sequential)] public struct INPUT {public uint type;public INPUT_UNION value;}
        public delegate bool MonitorEnum(IntPtr monitor,IntPtr dc,ref RECT rect,IntPtr unused);
        [DllImport("kernel32.dll",SetLastError=true)]public static extern IntPtr GetCurrentProcess();
        [DllImport("kernel32.dll",SetLastError=true)]public static extern bool CloseHandle(IntPtr handle);
        [DllImport("kernel32.dll",SetLastError=true)]public static extern IntPtr LocalFree(IntPtr handle);
        [DllImport("kernel32.dll",SetLastError=true)]public static extern IntPtr OpenProcess(uint access,bool inherit,uint pid);
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]public static extern bool QueryFullProcessImageName(IntPtr process,uint flags,StringBuilder name,ref uint size);
        [DllImport("kernel32.dll",SetLastError=true)]public static extern bool ProcessIdToSessionId(uint pid,out uint session);
        [DllImport("kernel32.dll")]public static extern uint WTSGetActiveConsoleSessionId();
        [DllImport("advapi32.dll",SetLastError=true)]public static extern bool OpenProcessToken(IntPtr process,uint access,out IntPtr token);
        [DllImport("advapi32.dll",SetLastError=true)]public static extern bool DuplicateTokenEx(IntPtr token,uint access,IntPtr attributes,int level,int type,out IntPtr primary);
        [DllImport("advapi32.dll",SetLastError=true)]public static extern bool SetTokenInformation(IntPtr token,int type,ref uint value,int size);
        [DllImport("advapi32.dll",SetLastError=true)]static extern bool AdjustTokenPrivileges(IntPtr token,bool disableAll,IntPtr state,uint size,IntPtr previous,IntPtr needed);
        public static void AdjustTokenPrivilegesDisable(){IntPtr token;if(!OpenProcessToken(GetCurrentProcess(),0x28,out token))throw new System.ComponentModel.Win32Exception();try{if(!AdjustTokenPrivileges(token,true,IntPtr.Zero,0,IntPtr.Zero,IntPtr.Zero))throw new System.ComponentModel.Win32Exception();}finally{CloseHandle(token);}}
        [DllImport("kernel32.dll",SetLastError=true)]public static extern bool InitializeProcThreadAttributeList(IntPtr list,int count,uint flags,ref IntPtr size);
        [DllImport("kernel32.dll",SetLastError=true)]public static extern bool UpdateProcThreadAttribute(IntPtr list,uint flags,IntPtr attribute,IntPtr value,IntPtr size,IntPtr previous,IntPtr needed);
        [DllImport("kernel32.dll")]public static extern void DeleteProcThreadAttributeList(IntPtr list);
        [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)]public static extern bool CreateProcessAsUser(IntPtr token,string app,StringBuilder command,IntPtr processAttributes,IntPtr threadAttributes,bool inherit,uint flags,IntPtr environment,string directory,ref STARTUPINFOEX startup,out PROCESS_INFORMATION process);
        [DllImport("kernel32.dll",SetLastError=true)]public static extern uint ResumeThread(IntPtr thread);
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]public static extern IntPtr CreateJobObject(IntPtr attributes,string name);
        [DllImport("kernel32.dll",SetLastError=true)]public static extern bool SetInformationJobObject(IntPtr job,int info,ref JOB_LIMIT limit,uint size);
        [DllImport("kernel32.dll",SetLastError=true)]public static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
        [DllImport("kernel32.dll",SetLastError=true)]public static extern uint WaitForSingleObject(IntPtr handle,uint milliseconds);
        [DllImport("kernel32.dll",SetLastError=true)]public static extern bool TerminateProcess(IntPtr handle,uint code);
        [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)]public static extern bool ConvertStringSecurityDescriptorToSecurityDescriptor(string text,uint revision,out IntPtr descriptor,out uint size);
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]public static extern IntPtr CreateNamedPipe(string name,uint open,uint mode,uint instances,uint output,uint input,uint timeout,ref SECURITY_ATTRIBUTES security);
        [DllImport("kernel32.dll",SetLastError=true)]public static extern bool GetNamedPipeClientProcessId(SafePipeHandle pipe,out uint pid);
        [DllImport("kernel32.dll",SetLastError=true)]public static extern bool PeekNamedPipe(SafePipeHandle pipe,IntPtr buffer,uint size,IntPtr read,out uint available,IntPtr remaining);
        [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)]public static extern IntPtr OpenSCManager(string machine,string database,uint access);
        [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)]public static extern IntPtr OpenService(IntPtr manager,string name,uint access);
        [DllImport("advapi32.dll",CharSet=CharSet.Unicode,SetLastError=true)]public static extern IntPtr CreateService(IntPtr manager,string name,string display,uint access,uint type,uint start,uint error,string binary,string group,IntPtr tag,string dependencies,string account,string password);
        [DllImport("advapi32.dll",SetLastError=true)]public static extern bool StartService(IntPtr service,uint count,IntPtr arguments);
        [DllImport("advapi32.dll",SetLastError=true)]public static extern bool ControlService(IntPtr service,uint control,out SERVICE_STATUS status);
        [DllImport("advapi32.dll",SetLastError=true)]public static extern bool DeleteService(IntPtr service);
        [DllImport("advapi32.dll")]public static extern bool CloseServiceHandle(IntPtr handle);
        [DllImport("user32.dll",SetLastError=true)]public static extern IntPtr OpenInputDesktop(uint flags,bool inherit,uint access);
        [DllImport("user32.dll",SetLastError=true)]public static extern bool SetThreadDesktop(IntPtr desktop);
        [DllImport("user32.dll",SetLastError=true)]public static extern bool CloseDesktop(IntPtr desktop);
        [DllImport("user32.dll",CharSet=CharSet.Unicode,SetLastError=true,EntryPoint="GetUserObjectInformationW")]public static extern bool GetUserObjectInformation(IntPtr handle,int info,StringBuilder buffer,uint size,out uint needed);
        [DllImport("user32.dll")]public static extern bool SetProcessDpiAwarenessContext(IntPtr context);
        [DllImport("user32.dll")]public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
        [DllImport("user32.dll")]public static extern int GetSystemMetrics(int index);
        [DllImport("user32.dll",SetLastError=true)]public static extern bool EnumDisplayMonitors(IntPtr dc,IntPtr clip,MonitorEnum callback,IntPtr data);
        [DllImport("user32.dll")]public static extern IntPtr GetDC(IntPtr window);
        [DllImport("user32.dll")]public static extern int ReleaseDC(IntPtr window,IntPtr dc);
        [DllImport("gdi32.dll")]public static extern IntPtr CreateCompatibleDC(IntPtr dc);
        [DllImport("gdi32.dll")]public static extern IntPtr CreateCompatibleBitmap(IntPtr dc,int width,int height);
        [DllImport("gdi32.dll")]public static extern IntPtr SelectObject(IntPtr dc,IntPtr item);
        [DllImport("gdi32.dll")]public static extern bool DeleteDC(IntPtr dc);
        [DllImport("gdi32.dll")]public static extern bool DeleteObject(IntPtr item);
        [DllImport("gdi32.dll")]public static extern int SetStretchBltMode(IntPtr dc,int mode);
        [DllImport("gdi32.dll",SetLastError=true)]public static extern bool StretchBlt(IntPtr target,int x,int y,int width,int height,IntPtr source,int sx,int sy,int sw,int sh,uint operation);
        [DllImport("gdi32.dll",SetLastError=true)]public static extern uint GetDIBits(IntPtr dc,IntPtr bitmap,uint first,uint count,byte[] bits,ref BITMAPINFO info,uint usage);
        [DllImport("user32.dll",SetLastError=true)]public static extern uint SendInput(uint count,INPUT[] inputs,int size);
    }

    static class Program {
        static int Tests(){int tests=0;Action<byte[]> valid=delegate(byte[] p){Wire.Validate(p);tests++;};Action<byte[]> invalid=delegate(byte[] p){try{Wire.Validate(p);}catch(InvalidDataException){tests++;return;}throw new Exception("Invalid request accepted");};
            valid(new byte[]{1});valid(new byte[]{2});valid(new byte[]{5});valid(new byte[]{6});valid(new byte[]{4,5});invalid(new byte[]{0});invalid(new byte[]{99});invalid(new byte[]{1,0});invalid(new byte[]{6,0});invalid(new byte[]{4,2,0,0,1});invalid(new byte[]{4,3,6,1});
            using(MemoryStream s=new MemoryStream())using(BinaryWriter w=new BinaryWriter(s)){w.Write((byte)3);w.Write(1);w.Write((ushort)1920);w.Write((ushort)1080);w.Write((byte)1);byte[] p=s.ToArray();valid(p);p[9]=0;invalid(p);p[9]=1;p[5]=255;p[6]=255;invalid(p);}
            using(MemoryStream s=new MemoryStream())using(BinaryWriter w=new BinaryWriter(s)){w.Write((byte)4);w.Write((byte)1);w.Write(.25);w.Write(.75);byte[] p=s.ToArray();valid(p);Array.Copy(BitConverter.GetBytes(Double.NaN),0,p,2,8);invalid(p);Array.Copy(BitConverter.GetBytes(Double.PositiveInfinity),0,p,2,8);invalid(p);Array.Copy(BitConverter.GetBytes(-.1),0,p,2,8);invalid(p);}
            valid(new byte[]{4,2,65,0,1});invalid(new byte[]{4,2,65,0,2});invalid(new byte[]{4,2,44,1,1});
            using(MemoryStream s=new MemoryStream())using(BinaryWriter w=new BinaryWriter(s)){w.Write((byte)4);w.Write((byte)3);w.Write((byte)0);w.Write((byte)1);w.Write(.5);w.Write(.5);byte[] p=s.ToArray();valid(p);p[2]=5;invalid(p);p[2]=0;p[3]=2;invalid(p);}
            valid(new byte[]{4,4,120,0,0,0});invalid(new byte[]{4,4,255,255,0,0});
            using(MemoryStream s=new MemoryStream()){Wire.Write(s,new byte[]{1},512);s.Position=0;if(Wire.Read(s,512)[0]!=1)throw new Exception("Framing");tests++;}
            using(MemoryStream s=new MemoryStream(new byte[]{1,0,0,1})){try{Wire.Read(s,512);throw new Exception("Limit");}catch(InvalidDataException){tests++;}}
            using(MemoryStream s=new MemoryStream(new byte[]{2,0,0,0,1})){try{Wire.Read(s,512);throw new Exception("Truncated packet");}catch(EndOfStreamException){tests++;}}
            if(Marshal.SizeOf(typeof(Native.INPUT))!=40 || Marshal.SizeOf(typeof(Native.WINTRUST_DATA))!=80)throw new Exception("Native layout");tests++;
            Native.RECT left=new Native.RECT();left.Left=-1920;left.Top=0;left.Right=0;left.Bottom=1080;Native.RECT all=left;all.Right=1920;
            int[] start=DesktopAgent.Project(left,all,0,0),end=DesktopAgent.Project(left,all,1,1);
            if(start[0]!=0 || start[1]!=0 || end[0]<32740 || end[0]>32780 || end[1]!=65535)throw new Exception("Physical multi-monitor coordinates");tests++;
            Config c=new Config();c.OwnerSid=WindowsIdentity.GetCurrent().User.Value;c.ClientPath=Path.Combine(Path.GetTempPath(),"Desk.exe");c.ClientHash=new String('0',64);c.ServiceHash=Trust.Hash(Trust.Exe);c.TrustMode="fixed";c.Validate();tests++;
            c.ServiceHash=new String('0',64);try{c.Validate();throw new Exception("Changed service accepted");}catch(UnauthorizedAccessException){tests++;}
            Console.WriteLine("{\"passed\":true,\"tests\":"+tests+",\"privileged_actions\":false}");return 0;
        }
        static int Main(string[] args){try{
                if(args.Length==1 && args[0]=="--self-test")return Tests();
                if(args.Length==1 && args[0]=="--service"){if(!Trust.IsSystem)throw new UnauthorizedAccessException("System service required");Config c=Config.Load();ServiceBase.Run(new Broker(c));return 0;}
                if(args.Length==5 && args[0]=="--agent"){DesktopAgent.Run(args[1],args[2],UInt32.Parse(args[3]),UInt32.Parse(args[4]));return 0;}
                if(args.Length==3 && args[0]=="--install"){Config.Install(args[1],args[2]);return 0;}
                if(args.Length==2 && args[0]=="--preflight"){string publisher=Trust.SignedPublisher(Trust.Exe);if(Trust.SignedPublisher(args[1])!=publisher)throw new UnauthorizedAccessException("Matching publisher required");return 0;}
                if(args.Length==4 && args[0]=="--preflight-fixed"){if(args[1].Length!=64 || args[2].Length!=64 || Trust.Hash(Trust.Exe)!=args[1] || Trust.Hash(args[3])!=args[2] || !String.Equals(Path.GetFileName(args[3]),"Desk.exe",StringComparison.OrdinalIgnoreCase))throw new UnauthorizedAccessException("Explicit package versions required");return 0;}
                if(args.Length==2 && args[0]=="--install-client"){Trust.Admin();string sid=((SecurityIdentifier)File.GetAccessControl(args[1]).GetOwner(typeof(SecurityIdentifier))).Value;Config.Install(sid,args[1]);return 0;}
                if(args.Length==3 && args[0]=="--install-fixed"){Trust.Admin();string sid=((SecurityIdentifier)File.GetAccessControl(args[1]).GetOwner(typeof(SecurityIdentifier))).Value;Config.Install(sid,args[1],args[2]);return 0;}
                if(args.Length==1 && args[0]=="--uninstall"){Config.Remove();return 0;}
                Console.Error.WriteLine("DeskHost requires an administrator-approved publisher or fixed-version installation. --self-test never touches the desktop.");return 2;
            }catch(Exception error){Console.Error.WriteLine("DeskHost: "+error.GetType().Name+". Installation or service authorization is unavailable.");return 20;}
        }
    }
}
