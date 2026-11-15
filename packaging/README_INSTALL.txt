DESK 0.13.0 — PREPARAÇÃO DO SERVIÇO DE TELA DE BLOQUEIO

Esta é uma prévia para assinatura e validação. O serviço não está ativado.
O programa principal mantém as correções de mouse, som e atualizações.

O novo componente permite que o aplicativo já aberto, em uma sessão remota
autorizada com mouse e teclado, solicite captura e entrada na tela de senha
através de um serviço local. Ele não remove nem armazena a senha do Windows.
Não oferece conexão antes do primeiro login do proprietário neste computador.

São necessários: assinatura Authenticode confiável no Desk e no serviço,
instalação do serviço com aprovação de administrador, e teste físico real.
Sem isso, a sessão continua limitada ao desktop desbloqueado. O instalador
do serviço verifica as assinaturas antes de registrar qualquer serviço.

O pacote público não contém credenciais de relay, identidades ou senhas.
Atualizações do aplicativo com o mesmo certificado e caminho continuam
permitidas; mudanças do certificado ou do serviço requerem nova aprovação.
A assinatura gratuita da Microsoft Store cobre o pacote MSIX distribuído
pela Store; não é uma assinatura avulsa deste instalador EXE.
