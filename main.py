import os
import webbrowser
import socketserver
import pyfiglet
import time
import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import box
from rich.table import Table
from rich.layout import Layout
from rich.live import Live
from datetime import datetime
import subprocess
import logging
import psutil
from http.server import SimpleHTTPRequestHandler
import signal

class TempMailViewer:
    def __init__(self):
        self.console = Console()
        self.API_URL = "https://www.1secmail.com/api/v1/"
        self.email = None
        self.seen_ids = set()
        self.layout = Layout()
        self.httpd = None

    def clear_screen(self):
        os.system("cls" if os.name == "nt" else "clear")

    def display_banner(self):
        figlet_banner = pyfiglet.figlet_format(" TempMail", font="slant")
        full_banner = figlet_banner + "\n  Unlimited TempMail powered by Wanz Xploit"
        
        # Gabungkan keduanya dalam satu Panel dengan gaya center
        self.console.print(Panel(full_banner, style="bold cyan", expand=True, padding=(0, 2), box=box.ROUNDED))

    def create_inbox_table(self, messages):
        table = Table(
            title="Inbox",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
            expand=True
        )
        table.add_column("ID", style="dim", width=6)
        table.add_column("From", style="bright_blue")
        table.add_column("Subject", style="bright_green")
        table.add_column("Date", style="yellow")
        
        for msg in messages:
            date = datetime.strptime(msg['date'], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')
            table.add_row(
                str(msg['id']),
                msg['from'],
                msg['subject'] if msg['subject'] else '[No Subject]',
                date
            )
        
        return table

    def format_html_content(self, html_content):
        styled_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    margin: 20px;
                    color: #333;
                }}
                .email-container {{
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                }}
                .email-header {{
                    background: #f5f5f5;
                    padding: 10px;
                    margin-bottom: 20px;
                    border-radius: 3px;
                }}
                .email-body {{
                    padding: 10px;
                }}
            </style>
        </head>
        <body>
            <div class="email-container">
                {html_content}
            </div>
        </body>
        </html>
        """
        return styled_html

    def display_email(self, message):
        if not message:
            return

        header_table = Table(
            box=box.ROUNDED,
            show_header=False,
            expand=True,
            title="Email Details",
            title_style="bold cyan"
        )
        
        header_table.add_column("Field", style="bold cyan", width=10)
        header_table.add_column("Value", style="bright_white")
        
        header_table.add_row("From", message['from'])
        header_table.add_row("Date", message.get('date', 'N/A'))
        header_table.add_row("Subject", message['subject'])
        
        self.console.print(header_table)
        
        if 'textBody' in message and message['textBody']:
            content_panel = Panel(
                message['textBody'],
                title="Message Content",
                style="bright_white",
                box=box.ROUNDED,
                padding=(1, 2)
            )
            self.console.print(content_panel)
        elif 'htmlBody' in message and message['htmlBody']:
            html_content = self.format_html_content(message['htmlBody'])
            html_file = "email_content.html"
            
            with open(html_file, "w", encoding='utf-8') as f:
                f.write(html_content)
            
            self.console.print(Panel(
                "[bold cyan]Opening HTML content in browser...[/bold cyan]",
                style="cyan",
                box=box.ROUNDED
            ))
            self.start_local_server(html_file)
            return
        else:
            self.console.print(Panel("[No Content]", style="dim"))

    def generate_email(self):
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]Generating temporary email..."),
            transient=True,
        ) as progress:
            progress.add_task("generate", total=None)
            response = requests.get(f"{self.API_URL}?action=genRandomMailbox")

        if response.status_code == 200:
            self.email = response.json()[0]
            self.console.print(
                Panel(
                    f"[bold green]Email Address:[/bold green] {self.email}",
                    title="Email Generated Successfully",
                    style="green",
                    box=box.ROUNDED,
                )
            )
            return True
        else:
            self.console.print(
                Panel(
                    "[bold red]Failed to generate email address![/bold red]",
                    style="red",
                    box=box.ROUNDED,
                )
            )
            return False

    def check_inbox(self):
        if not self.email:
            return []

        username, domain = self.email.split("@")
        try:
            response = requests.get(
                f"{self.API_URL}?action=getMessages&login={username}&domain={domain}",
                timeout=10,
            )
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            self.console.print(f"[bold red]Error checking inbox: {str(e)}[/bold red]")
        return []

    def read_email(self, message_id):
        username, domain = self.email.split("@")
        try:
            response = requests.get(
                f"{self.API_URL}?action=readMessage&login={username}&domain={domain}&id={message_id}",
                timeout=10,
            )
            if response.status_code == 200:
                return response.json()
        except requests.exceptions.RequestException as e:
            self.console.print(f"[bold red]Error reading message: {str(e)}[/bold red]")
        return None

    def kill_port(self, port):
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for conn in proc.net_connections(kind='inet'):
                    if conn.laddr.port == port:
                        proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

    def start_local_server(self, html_file):
        html_file_path = os.path.abspath(html_file)
        
        if not os.path.exists(html_file_path):
            self.console.print(f"[bold red]Error: File {html_file} tidak ditemukan![/bold red]")
            return

        self.kill_port(8080)

        os.chdir(os.path.dirname(html_file_path))

        class SilentHandler(SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

        try:
            with socketserver.TCPServer(("", 8080), SilentHandler) as httpd:
                webbrowser.open(f"http://localhost:8080/{os.path.basename(html_file_path)}")
                self.console.print(Panel(
                    f"[bold cyan]View HTML email content at: [yellow]http://localhost:8080/{os.path.basename(html_file_path)}[/yellow]",
                    style="bold cyan",
                    box=box.ROUNDED,
                ))
                self.console.print(Panel(
                    "[bold cyan]Press [yellow]CTRL + C[/yellow] to stop the server.[/bold cyan]",
                    style="cyan",
                    box=box.ROUNDED,
                ))
                httpd.serve_forever()
        except Exception as e:
            self.console.print(f"[bold red]Error starting local server: {str(e)}[/bold red]")

    def stop_local_server(self):
        if self.httpd:
            self.httpd.shutdown()
            self.console.print("[bold red]Local server stopped.[/bold red]")

    def run(self):
        self.clear_screen()
        self.display_banner()

        if not self.generate_email():
            return

        try:
            shown_message_once = False
            with Live(auto_refresh=False) as live:
                while True:
                    messages = self.check_inbox()
                    new_messages = [msg for msg in messages if msg["id"] not in self.seen_ids]

                    if new_messages:
                        self.clear_screen()
                        self.display_banner()
                        
                        inbox_table = self.create_inbox_table(messages)
                        live.update(inbox_table, refresh=True)

                        for msg in new_messages:
                            self.seen_ids.add(msg["id"])
                            self.console.print("\n ")
                            full_message = self.read_email(msg["id"])
                            self.display_email(full_message)

                    if not shown_message_once:
                        self.console.print(
                            Panel(
                                "[bold cyan]Press [yellow]CTRL + C[/yellow] to stop the application at any time.[/bold cyan]",
                                style="cyan",
                                box=box.ROUNDED,
                            )
                        )
                        shown_message_once = True

                    time.sleep(5)

        except KeyboardInterrupt:
            self.clear_screen()
            self.console.print(
                Panel(
                    "[bold yellow]Thank you for using TempMail Viewer![/bold yellow]",
                    style="yellow",
                    box=box.ROUNDED,
                )
            )

if __name__ == "__main__":
    viewer = TempMailViewer()
    viewer.run()