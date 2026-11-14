# Code signing policy

## Estado atual

O Desk está preparando uma candidatura à SignPath Foundation. Não foi aprovado e não possui certificado fornecido por ela. Releases atuais são identificadas como **unsigned / sem assinatura**. Nenhum arquivo deve ser apresentado como assinado antes de uma assinatura válida ser verificada.

## Responsabilidades

- Committer e revisor: [Danilo412](https://github.com/Danilo412).
- Aprovador de futuras solicitações de assinatura: [Danilo412](https://github.com/Danilo412).
- Autenticação multifator nas contas do repositório e de assinatura será requisito antes de habilitar qualquer acesso de assinatura; sua configuração ainda precisa ser confirmada.

Só poderão ser assinados artefatos gerados do código deste repositório e por um fluxo de compilação verificável. Cada release exigirá aprovação manual do mantenedor. Chaves privadas e credenciais de assinatura não serão exportadas ou incluídas no repositório. Bibliotecas de terceiros manterão suas próprias assinaturas ou permanecerão sem assinatura, conforme as regras do programa.

## Artefatos pretendidos

O pedido abrange o executável próprio `Desk.exe`, o instalador Windows e o desinstalador gerados a partir deste projeto, com produto Desk e versão consistente. Dependências de terceiros não devem ser reassinadas como se fossem mantidas pelo projeto.

O fluxo público atual apenas compila e testa arquivos sem assinatura. Uma integração de assinatura só será habilitada depois da aceitação, configuração segura do serviço e revisão das permissões. A página de release deverá mostrar o resultado da verificação e identificar a origem da compilação.

Se o projeto for aceito e passar efetivamente a usar o programa, os créditos exigidos serão adicionados às releases assinadas: “Free code signing provided by SignPath.io, certificate by SignPath Foundation”. Esta frase descreve uma condição futura, não um serviço já concedido ao Desk.

## Privacidade

Veja [PRIVACY.md](PRIVACY.md). O aplicativo não incorpora credenciais de terceiros nas releases públicas. A configuração particular preparada para uso pessoal não será publicada como artefato deste repositório.
