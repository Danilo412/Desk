DESK 0.14.0 — PRÉVIA DO ACESSO POR NÚMERO E SENHA

Atualize o aplicativo nas duas pontas com Desk-0.14.0-Update.exe.
O número fixo, a configuração de internet e os acessos salvos são preservados.

No computador que receberá o acesso, abra Configurações > Acesso sem supervisão.
Use “Definir ou trocar senha de acesso” e crie uma senha exclusiva do Desk,
com 12 a 128 caracteres. Depois marque a opção de permitir acesso por número
e senha e confira a confirmação. Ninguém define ou ativa essa senha por você.
Na outra máquina, digite os 12 números e conecte: o Desk pedirá a senha.
Não é necessário aceitar nessa ponta a cada conexão. O número sozinho não
autoriza acesso. As permissões de mouse/teclado, áudio e área de transferência
selecionadas pelo proprietário continuam valendo.

A senha não é salva no computador que conecta. O host guarda um verificador
com salt, protegido junto à identidade local. A senha só é enviada dentro
da conexão criptografada, depois da conferência da identidade do destino.
Cinco tentativas erradas impõem espera de cinco minutos nesta execução.
Desativar, trocar ou remover a senha encerra as sessões que a utilizaram.
Dispositivos autorizados separadamente continuam usando suas próprias chaves.

Mantenha o computador ligado e o Desk aberto após o login. A opção “Iniciar
com o Windows, após meu login” é configurada localmente pelo proprietário.
Esta prévia não oferece acesso antes do primeiro login nem remove a senha
do Windows. A senha do Desk e a senha do Windows são diferentes.

TELAS PROTEGIDAS E ADMINISTRADOR
O aplicativo comum permanece sem elevação. O serviço opcional, aprovado por
administrador e vinculado ao Desk.exe exato, fornece captura e entrada nas
telas protegidas durante sessões autorizadas. Não é necessário executar
toda a interface como administrador a cada abertura.
Para atualizar o serviço, remova apenas “Desk - Serviço de tela de bloqueio”
antigo, instale o aplicativo novo e depois Desk-Service-0.14.0-Setup.exe.
Selecione o Desk.exe novo e aprove a versão exata para teste pessoal.
O Windows continuará exigindo as aprovações pertinentes. Não são criadas
exceções de antivírus, certificados raiz ou desvios das proteções do sistema.

Os instaladores são uma prévia sem assinatura digital. O canal estável não
foi alterado. Os testes reais de senha entre os dois PCs e de tela bloqueada
precisam ser concluídos com o proprietário. Não envie senhas pelo chat.
O pacote público não contém identidades nem credenciais privadas de relay.
