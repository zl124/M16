import os
import smtplib
from email.message import EmailMessage

def test_email():
    # Carregar do ambiente (Render)
    smtp_server = "gabrielcrodrigues74@gmail.com"
    smtp_port = 587
    username = os.environ.get("MAIL_USERNAME")
    password = os.environ.get("MAIL_PASSWORD") # A Palavra-passe de aplicação

    if not username or not password:
        print("ERRO: Variáveis MAIL_USERNAME ou MAIL_PASSWORD não encontradas!")
        return

    print(f"Tentando ligar a {smtp_server}:{smtp_port} como {username}...")

    msg = EmailMessage()
    msg.set_content("Email de teste enviado do Render para validar a configuração SMTP. 🚀")
    msg["Subject"] = "Teste de Email - E-Lixo Zero"
    msg["From"] = username
    msg["To"] = "gabrielcrodrigues2008@gmail.com"

    try:
        # TLS (Porta 587)
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
        print("SUCESSO! O email foi enviado corretamente.")
    except Exception as e:
        print(f"FALHA NO ENVIO: {str(e)}")
        print("\nDICA: Se o erro for '535 Authentication Failed', a sua App Password do Google pode estar errada ou expirada.")

if __name__ == "__main__":
    test_email()
