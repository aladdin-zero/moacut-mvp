using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Windows.Forms;

class Launcher {
    static Process backend;
    static string url, logFile;
    static readonly object logLock = new object();
    static void Log(string text) { if(text==null)return;lock(logLock)File.AppendAllText(logFile,text+Environment.NewLine,Encoding.UTF8); }
    static string Quote(string text) { return "\""+text.Replace("\"","")+"\""; }
    static void Open(string target) { Process.Start(new ProcessStartInfo(target){UseShellExecute=true}); }
    static void Stop() {
        if(backend==null || backend.HasExited)return;
        try {
            var request=(HttpWebRequest)WebRequest.Create(url+"/api/stop");
            request.Proxy=null;request.Method="POST";request.ContentType="application/json";request.Timeout=16000;
            byte[] body=Encoding.UTF8.GetBytes("{}");request.ContentLength=body.Length;
            using(var stream=request.GetRequestStream())stream.Write(body,0,body.Length);
            using(var response=request.GetResponse()){}
        } catch(Exception e) {Log(e.GetType().Name+": stop request failed");}
        if(!backend.HasExited){backend.Kill();backend.WaitForExit(5000);}
    }
    [STAThread] static int Main(string[] args) {
        Application.EnableVisualStyles();
        bool check=args.Length==2 && args[0]=="--check";
        string data=check?Path.GetFullPath(args[1]):Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"MOACUT");
        Directory.CreateDirectory(data);Directory.CreateDirectory(Path.Combine(data,"logs"));
        logFile=Path.Combine(data,"logs","moacut-"+DateTime.Now.ToString("yyyyMMdd")+".log");
        bool first;
        using(var mutex=new Mutex(true,check?"Local\\MOACUT_PACKAGE_CHECK":"Local\\MOACUT_MVP",out first)) {
            string endpoint=Path.Combine(data,"endpoint.txt");
            if(!first) {
                if(File.Exists(endpoint)){
                    int port;if(Int32.TryParse(File.ReadAllText(endpoint),out port)&&port>0&&port<65536)Open("http://127.0.0.1:"+port);
                } else MessageBox.Show("모아컷이 이미 실행 중입니다. 작업 표시줄의 모아컷 아이콘에서 열어 주세요.","모아컷");
                return 0;
            }
            try {
                string root=AppDomain.CurrentDomain.BaseDirectory;
                string python=Path.Combine(root,"runtime","python.exe"), server=Path.Combine(root,"app","server.py");
                if(!File.Exists(python)||!File.Exists(server))throw new IOException("ZIP 전체를 먼저 압축 해제한 뒤 MOACUT.exe를 실행해 주세요.");
                var reservation=new TcpListener(IPAddress.Loopback,0);reservation.Start();
                int port=((IPEndPoint)reservation.LocalEndpoint).Port;reservation.Stop();url="http://127.0.0.1:"+port;
                var start=new ProcessStartInfo(python,"-B -X utf8 "+Quote(server)+" --port "+port+" --data "+Quote(Path.Combine(data,"captures")));
                start.WorkingDirectory=root;start.UseShellExecute=false;start.CreateNoWindow=true;
                start.RedirectStandardOutput=true;start.RedirectStandardError=true;
                start.StandardOutputEncoding=Encoding.UTF8;start.StandardErrorEncoding=Encoding.UTF8;
                start.EnvironmentVariables.Remove("PYTHONHOME");start.EnvironmentVariables.Remove("PYTHONPATH");
                start.EnvironmentVariables["PYTHONUTF8"]="1";start.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"]="1";
                start.EnvironmentVariables["HF_HUB_OFFLINE"]="1";start.EnvironmentVariables["TRANSFORMERS_OFFLINE"]="1";
                backend=new Process();backend.StartInfo=start;
                backend.OutputDataReceived+=(s,e)=>Log(e.Data);backend.ErrorDataReceived+=(s,e)=>Log(e.Data);
                backend.Start();backend.BeginOutputReadLine();backend.BeginErrorReadLine();
                bool ready=false;
                for(int i=0;i<120&&!backend.HasExited;i++) {
                    try {
                        var request=(HttpWebRequest)WebRequest.Create(url+"/api/state");request.Proxy=null;request.Timeout=500;
                        using(var response=request.GetResponse())using(var reader=new StreamReader(response.GetResponseStream()))
                            ready=reader.ReadToEnd().Contains("\"MOACUT\"");
                        if(ready)break;
                    }catch(WebException){}
                    Thread.Sleep(250);
                }
                if(!ready)throw new IOException("프로그램을 시작하지 못했습니다. 환경점검.cmd를 실행하거나 아래 로그를 확인해 주세요.\n"+logFile);
                File.WriteAllText(endpoint,port.ToString());
                if(check){File.WriteAllText(Path.Combine(data,"launcher-check.txt"),"ready "+url);return 0;}
                using(var tray=new NotifyIcon()) {
                    tray.Icon=SystemIcons.Application;tray.Text="모아컷 · MOACUT";
                    var menu=new ContextMenuStrip();menu.Items.Add("모아컷 열기",null,(s,e)=>Open(url));
                    menu.Items.Add("작업 데이터 폴더",null,(s,e)=>Open(data));
                    menu.Items.Add("모아컷 종료",null,(s,e)=>Application.Exit());
                    tray.ContextMenuStrip=menu;tray.DoubleClick+=(s,e)=>Open(url);tray.Visible=true;
                    Open(url);
                    var monitor=new System.Windows.Forms.Timer();monitor.Interval=2000;
                    monitor.Tick+=(s,e)=>{if(backend.HasExited){MessageBox.Show("모아컷이 종료되었습니다. 다시 실행하거나 환경점검.cmd를 확인해 주세요.","모아컷");Application.Exit();}};
                    monitor.Start();Application.Run();monitor.Dispose();tray.Visible=false;
                }
                return 0;
            } catch(Exception e) {Log(e.ToString());if(!check)MessageBox.Show(e.Message,"모아컷 실행 확인");return 1;}
            finally {Stop();if(File.Exists(endpoint))File.Delete(endpoint);}
        }
    }
}
