DESK 0.12.5 — CONTROLE E CURSOR

Atualize as DUAS pontas. Os comandos de mouse e teclado usam um canal
WebRTC separado, confiável e ordenado, protegido por uma chave temporária
negociada dentro da sessão TLS já autorizada. Clientes antigos continuam
compatíveis pelo transporte anterior. Não há alteração nas permissões.

Durante o controle, a captura MSS exclui o cursor da imagem para evitar
um ponteiro pequeno e atrasado acompanhando o cursor local imediato.
Permanecem as correções de escala, redimensionamento e tela cheia da 0.12.4.

TELA DE BLOQUEIO
Esta versão NÃO controla a tela de login ou o desktop protegido do Windows.
O aplicativo ainda não possui um serviço de sistema para esse recurso.
O Desk informa o bloqueio e preserva a conexão; desbloqueie diretamente na
outra máquina. O controle volta com as mesmas permissões após desbloquear.
Recusas de entrada do Windows não encerram mais a sessão inteira.

ATUALIZAÇÕES
Menu > Configurações > Atualizações ou Menu > Verificar atualizações.
O Windows pode impedir a execução: o pacote ainda não tem Authenticode.
A assinatura do manifesto de atualização não substitui Authenticode.
O instalador preserva número, favoritos e configurações existentes.
O pacote público NÃO inclui credenciais de relay ou identidades privadas.
