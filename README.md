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

O Desk instalado verifica atualizações ao abrir e a cada seis horas. O usuário confirma o download e a abertura do instalador. Uma sessão ou gravação ativa impede a instalação. Consulte [ATUALIZACOES.md](ATUALIZACOES.md).
