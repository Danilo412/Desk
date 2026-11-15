# Desk

Aplicativo independente de suporte remoto consentido para Windows, com endereço numérico fixo por perfil do usuário, conexão TLS 1.3, seleção de monitores, conversa e envio de arquivos.

O projeto é mantido por [Danilo412](https://github.com/Danilo412) e publicado sob GPL-3.0-or-later. Este repositório contém código próprio; não contém código-fonte ou binários do AnyDesk ou RustDesk.

## Downloads

[Versões públicas](https://github.com/Danilo412/Desk/releases) · [Compilação no GitHub Actions](https://github.com/Danilo412/Desk/actions/workflows/windows.yml)

As versões públicas são **sem assinatura digital** e **sem credenciais de serviços de conexão**. É necessário configurar seu próprio serviço de sinalização/relay para conectar pela internet. Não há promessa de disponibilidade permanente ou de aceitação automática pelo Windows.

## Funcionalidades

- Endereço de 12 dígitos derivado da identidade local e preservado ao reabrir o programa.
- Solicitação local de aceite, com permissões separadas para mouse/teclado, área de transferência e áudio.
- TLS 1.3 com certificado conferido pelo convite; consulta do endereço com oferta assinada e fixação da identidade após conexão aprovada.
- Imagem por DEFLATE e VP8, com perfis até 1080p/1440p e opções de fluidez; a origem, os computadores e a rede limitam o resultado.
- Monitores, tela cheia/Esc, conversa, arquivos com conferência de integridade e favoritos.
- Reconexão sem novo aceite somente para dispositivos explicitamente autorizados no computador acessado.

O computador precisa estar ligado, conectado e com o Desk aberto. A instalação não ativa acesso sem supervisão. O número é um identificador, não uma senha de acesso.

## Executar a partir do código

Windows 10/11 x64 e Python 3.12 x64:

```console
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-build.txt
.venv\Scripts\python -m pip install --no-deps -e .
.venv\Scripts\python iniciar.py
```

Para usar a internet, copie `internet.example.json` para `internet.json` **somente no seu computador**, preencha os dados dos serviços que você controla e mantenha configuração compatível nos clientes. O arquivo deve ficar ao lado de `Desk.exe` na edição compilada, ou na raiz do projeto na execução por código. Nunca faça commit desse arquivo.

A implementação atual usa o serviço de sinalização Metered Realtime e permite os endpoints TURN reconhecidos de Metered/ExpressTURN. Contas, limites e disponibilidade desses fornecedores são independentes deste projeto. Sem configuração, não há consulta pública do número pela internet.

## Compilar

```console
.venv\Scripts\python -m pytest tests -q
.venv\Scripts\python scripts\build_windows.py
.venv\Scripts\python scripts\build_installer.py
.venv\Scripts\python scripts\validate_package.py
```

O executável com dependências fica em `dist/Desk`; o instalador público e os arquivos para distribuição ficam em `dist/publish`. A compilação pública não incorpora `internet.json`, identidades ou senhas locais. O compilador do instalador é baixado de uma versão fixa do Inno Setup, com conferência de hash e assinatura do fornecedor.

## Validação e limites

O código 0.12.0 passou em 194 testes locais. A atualização inclui um aviso de nova versão, download verificado por manifesto Ed25519 e SHA-256, e confirmação local antes de abrir o instalador. O pacote de atualização mantém a configuração existente de internet e não contém credenciais. A versão 0.12.0 ainda precisa de uma primeira instalação em clientes antigos, que não possuem o atualizador. A abertura do novo executável foi bloqueada pelo Controle de Aplicativo no computador de desenvolvimento; o teste do instalador atualizado nesse Windows permanece pendente. A assinatura do manifesto não substitui Authenticode.

 Foram feitos testes sintéticos de 1080p/1440p por TURN público forçado, conferência dos pixels, alternância de codec, arquivo e comandos em backend simulado. O instalador particular anterior também passou em instalação/desinstalação e persistência de endereço. Esses ensaios foram feitos em um único computador com instâncias isoladas, e não equivalem a dois PCs físicos ou a um benchmark de FPS. A compilação pública tem seus próprios resultados no Actions.

## Code signing policy

A solicitação à SignPath Foundation foi recusada em **14 de novembro de 2026**. **Não há aprovação nem certificado concedido; os executáveis e instaladores atuais continuam sem assinatura Authenticode.** Veja [CODE_SIGNING.md](CODE_SIGNING.md). A autoria e a reputação do projeto são recentes; não alegamos adoção pública anterior.

## Privacidade e licença

[Política de privacidade](PRIVACY.md) · [Licença GPL-3.0-or-later](LICENSE) · licenças de dependências em `licencas/`.

Problemas gerais podem ser relatados em Issues. Não publique convites, credenciais, chaves privadas ou senhas nos relatos.

## Atualizações

O Desk instalado verifica atualizações ao abrir e a cada cinco minutos. O usuário confirma o download e a abertura do instalador. Uma sessão ou gravação ativa impede a instalação. Consulte [ATUALIZACOES.md](ATUALIZACOES.md).

## Correções 0.12.1

Favoritos e recentes são consolidados por identidade/endereço, mantendo o acesso autorizado e o nome escolhido. A migração guarda uma cópia protegida do perfil e não muda o número fixo. Limites do serviço são diferenciados de dispositivo ausente. A configuração salva do serviço volta a funcionar após reabrir mesmo sem internet.json; instalações novas mostram claramente quando precisam importar a configuração privada. O controle de consultas ao número usa uma janela curta e não um limite para toda a duração do convite. Três endereços sintéticos foram registrados simultaneamente no serviço público e localizados com uma quarta conexão; isso não substitui o teste do PC físico indisponível.

## Avisos e busca rápida — 0.12.2

A localização por número reaproveita a conexão de sinalização já aberta quando disponível. O pedido pode mostrar um aviso antecipado de preparação na outra ponta, antes da negociação da imagem. Esse aviso não aceita a sessão nem concede acesso. O primeiro aceite com a opção de reconexão autoriza somente a chave do dispositivo; revogação e permissões existentes são preservadas.

Mensagens e arquivos recebidos mostram um aviso discreto; pedidos de conexão, destino de arquivo e ações que exigem confirmação trazem a janela do Desk e o diálogo para a frente. Configurações > Notificações permite ajustar avisos, prévias e foco e fazer um teste local. O Windows ainda pode limitar ativação de janelas, especialmente em áreas de trabalho protegidas.

## Imagem, áudio e controle — 0.12.3

O controle de carga preserva resolução e quantização, adaptando FPS em vez de diminuir a nitidez. O codificador usa o tempo real dos quadros e permanece aberto durante a restauração estática sem perda. Decodificar vídeo não bloqueia diretamente a leitura do áudio e das mensagens.

As duas pontas negociam áudio Opus estéreo de 48 kHz em blocos de 20 ms, com reserva limitada para variações da rede. Clientes anteriores continuam usando o PCM legado. MP4 usa AAC estéreo a 48 kHz.

Movimentos têm envio final garantido após a limitação de frequência; cliques e teclas mantêm a ordem em uma fila fora da interface. A entrada no Windows usa SendInput, com coordenadas da área de trabalho virtual e botões laterais. Os fragmentos enviados são menores e alternam áudio, vídeo e arquivos; os fragmentos antigos continuam aceitos. Essas mudanças não concedem nem ampliam permissões.

A fluidez, o atraso e a fidelidade ainda dependem da rede, das máquinas e da escala de exibição. Não há promessa de qualidade idêntica ao AnyDesk nem de conexão sem interrupções.

O áudio usa um canal RTC independente, sem retransmissões de som atrasado, quando as duas pontas negociam esse recurso. Uma chave ChaCha20-Poly1305 aleatória e um prefixo de nonce são trocados dentro da sessão TLS já autenticada e aprovada. Contadores de 64 bits não se repetem por chave; pacotes sem autenticação ou repetidos são descartados. A chave não é gravada. Clientes anteriores mantêm o transporte TLS existente. O receptor revalida a permissão de áudio a cada pacote.

Referências de implementação: [FFmpeg](https://ffmpeg.org/ffmpeg-codecs.html), [aiortc](https://aiortc.readthedocs.io/en/stable/api.html), [AEAD](https://cryptography.io/en/latest/hazmat/primitives/aead/), [SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput).

## Mouse e atualizações — 0.12.4

A normalização SendInput usa a geometria física guardada pela captura, em um contexto de thread que evita virtualização por DPI. A escala lógica retornada por outra API não é misturada com pixels físicos. A conversão no cliente usa a geometria atual da imagem em vez do último retângulo pintado. Isso corrige cliques deslocados após redimensionar, alternar tela cheia ou usar monitores com escalas diferentes.

Configurações > Atualizações mostra a versão instalada, o estado da busca e o horário. Avisos de novas versões abrem essa página e a oferta de download. A consulta do manifesto evita reutilizar um redirecionamento antigo do GitHub, e um canal sem manifesto não é informado como uma instalação atualizada. Assinatura Ed25519, limites de origem, integridade e verificações do Windows são mantidos.

## Controle e cursor — 0.12.5

Em pares atualizados, mouse e teclado usam um RTCDataChannel confiável e ordenado separado do fluxo TLS de vídeo/arquivos. Uma chave e um prefixo aleatórios são negociados dentro do TLS após a aprovação da sessão; cada mensagem é autenticada com ChaCha20Poly1305 e um contador crescente. A mudança de rota usa uma barreira no TLS para não reordenar eventos anteriores. Duplicatas e mensagens adulteradas são rejeitadas; permissões continuam verificadas no receptor. Clientes antigos usam a rota TLS anterior. Uma falha depois da mudança encerra a sessão em vez de misturar rotas que possam reordenar teclas e botões.

Durante o controle, a captura MSS usa `with_cursor=False`, excluindo o cursor do vídeo. O ponteiro local responde imediatamente e recebe somente a forma do cursor remoto. O desktop protegido é consultado sem trocar desktops ou alterar permissões. O aplicativo avisa quando o Windows bloqueia a entrada e preserva a sessão. **O Desk ainda não oferece controle da tela de login/Winlogon, UAC ou um serviço privilegiado.** Desbloquear diretamente o computador remoto continua necessário. Authenticode permanece pendente; Windows pode bloquear instaladores e executáveis.

## Screen broker preview — 0.13.0

This branch prepares a separate Windows service for capture and typed input on protected desktops during an already-approved session. Distribution can use a trusted Authenticode publisher. A private pilot can instead explicitly bind the exact service/GUI versions in an administrator-owned installation. These IPC authorization hashes do not create Windows/WDAC exceptions; the binaries still must pass Windows checks. Every GUI update in fixed-version mode requires another administrative binding.

See [the trust boundary, setup and validation requirements](native/DeskHost/README.md). No privileged service has been activated by the build or protocol tests. Actual service installation and physical lock/unlock tests remain required. This is not a pre-login remote host and does not remove or store Windows passwords.
