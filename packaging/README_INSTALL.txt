DESK 0.14.4 — INTERFACE ASTRYX

Atualize o aplicativo nas duas pontas com Desk-0.14.4-Update.exe.
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
A versão 0.14.4 atualiza somente o aplicativo. O pacote não inclui
o serviço opcional de tela de bloqueio.
Um serviço anterior vinculado ao hash exato do Desk.exe deixa de reconhecer
o aplicativo atualizado. Portanto, o acesso à tela bloqueada e às janelas
protegidas por esse serviço fica pendente. Não remova o serviço existente
nem altere as proteções para tentar contornar o bloqueio. O controle comum
na área de trabalho aberta continua sujeito às permissões normais do Windows.
O Windows continuará exigindo as aprovações pertinentes. Não são criadas
exceções de antivírus, certificados raiz ou desvios das proteções do sistema.

Os instaladores são uma prévia sem assinatura digital. A distribuição será feita pelo canal oficial após a validação do pacote. Os testes reais de senha entre os dois PCs e de tela bloqueada
precisam ser concluídos com o proprietário. Não envie senhas pelo chat.
O pacote público não contém identidades nem credenciais privadas de relay.

FLUIDEZ (0.14.2)
Atualize as duas pontas para aproveitar a codificação otimizada e a fila de entrada no computador acessado.
Os testes de imagem foram feitos com dados sintéticos, não comprovam o FPS desta máquina.
A janela Informações da sessão passa a mostrar captura, codificação, fila de quadros e tempo de aplicação do controle.
Não altera senhas, número fixo, permissões do Windows nem ativa o serviço automaticamente.
A renovação do vínculo do serviço de versão exata fica pendente da liberação do novo componente.
Os arquivos novos continuam sem assinatura Authenticode e podem ser bloqueados pelo Windows.

CAPTURA COM CONTROLE (0.14.2)
A captura DXGI permanece habilitada quando o mouse e teclado estão permitidos, em configurações de monitor inequívocas.
Se falhar ou a saída não corresponder ao monitor, a captura MSS é mantida como alternativa.
O cursor separado continua sendo enviado sem compor o ponteiro de hardware sobre a imagem.
As etapas da captura agora mostram consulta, obtenção da imagem e redimensionamento.
A melhoria na máquina que antes apresentava captura de 141 ms exige teste real após atualizar.

INTERFACE ASTRYX
O endereço fixo e o botão de cópia aparecem juntos na tela inicial.
Os atalhos se reorganizam em janelas menores. Favoritos, configurações,
solicitações recebidas e controles da sessão usam o mesmo estilo.
A opção de reduzir animações continua disponível em Configurações > Aparência.
