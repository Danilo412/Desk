# Política de privacidade do Desk

Versão inicial: 14 de novembro de 2026. Responsável pelo projeto: [Danilo412](https://github.com/Danilo412).

## Tela, áudio e controle

O Desk transmite a tela durante uma sessão aprovada pelo computador acessado, ou por um dispositivo previamente autorizado quando o usuário habilitou o acesso sem supervisão. Mouse/teclado, áudio de saída e área de transferência dependem das permissões concedidas. A transmissão é destinada ao outro participante da sessão e passa pelo canal TLS 1.3 do aplicativo. Os participantes continuam responsáveis pelo conteúdo ao qual concedem acesso.

Arquivos enviados exigem escolha de destino, exceto quando o usuário ativou explicitamente a opção específica de recebimento para dispositivos autorizados. A conversa e o registro de atividades de transferência da interface ficam na memória da execução. Os arquivos que o usuário escolhe salvar permanecem no destino selecionado.

## Serviços de rede

A edição pública não inclui credenciais. O usuário configura um serviço compatível antes de usar conexões pela internet. Quando configurado, abrir/operar o Desk pode iniciar a publicação de disponibilidade do endereço, a troca de ofertas de conexão e a negociação de rotas de rede.

A implementação usa Metered Realtime para sinalização/consulta do endereço e pode usar STUN/TURN da configuração de Metered ou ExpressTURN. O serviço de sinalização transporta mensagens de negociação e ofertas cifradas/assinadas. Os provedores e participantes podem observar endereços IP, identificadores de conexão, horários e volume de tráfego. TURN retransmite o fluxo protegido pelo TLS interno; não recebe a chave privada da identidade do Desk. O número do Desk é compartilhável e não substitui o aceite ou a autorização de dispositivo.

Quem instala deve consultar os termos e políticas do provedor que escolher, em seus sites oficiais: [Metered](https://www.metered.ca/) e [ExpressTURN](https://www.expressturn.com/). O projeto não opera esses fornecedores nem controla seus registros, retenção, localização ou limites. Não há análise de uso, publicidade ou serviço de telemetria próprio do projeto no aplicativo.

## Dados locais

A identidade, chaves, autorizações, favoritos, preferências e referências a sessões recentes são armazenados no perfil Windows, normalmente em `%LOCALAPPDATA%\NovoAcesso`. O arquivo de identidade usa proteção DPAPI no Windows. O histórico recente não guarda o conteúdo completo dos convites. Os dados de identidade ficam separados da instalação para preservar o número nas atualizações/reinstalações; desinstalar o programa não os apaga automaticamente.

Credenciais de configuração podem existir em `internet.json` junto ao programa e nas configurações locais protegidas. Não compartilhe esses arquivos ou o arquivo de identidade. A edição pública não contém o login de nenhuma conta ou uma identidade pré-autorizada.

## Diagnósticos

Os modos de diagnóstico de conexão usam telas, comandos simulados e arquivos temporários sintéticos. Eles ainda podem conectar aos provedores configurados, que observam os metadados de rede correspondentes. Nenhum diagnóstico garante disponibilidade permanente ou compatibilidade com todo computador.

## Contato

Use os canais do [repositório](https://github.com/Danilo412/Desk) para dúvidas gerais, sem anexar segredos ou dados de tela. Esta política deverá ser revista se forem adicionados novos serviços ou formas de coleta de dados.
