/* =============================================================
   CONTRATOS DO DOMÍNIO
   -------------------------------------------------------------
   Em JS puro não há tipo em tempo de execução, então este arquivo
   cumpre dois papéis:
   1. documenta o formato que a API vai devolver (JSDoc — o editor
      completa e avisa quando o campo não existe);
   2. exporta as constantes que valem em código: papéis, permissões
      e a classificação administrativo x clínico.

   Nomes técnicos em inglês (igual ao banco e à API). O rótulo que
   o usuário lê vem de core/terms.js.
   ============================================================= */
(function (global) {
  "use strict";

  var VC = (global.VC = global.VC || {});

  /**
   * @typedef {Object} User            Credencial de acesso. Global: não pertence a um tenant.
   * @property {string}  id
   * @property {string}  email
   * @property {string}  name
   * @property {"pending"|"active"|"blocked"} status
   * @property {string|null} emailVerifiedAt
   *
   * @typedef {Object} Tenant          A conta: autônomo, consultório ou clínica.
   * @property {string}  id
   * @property {string}  name
   * @property {"solo"|"office"|"clinic"} type
   * @property {"trial"|"active"|"past_due"|"suspended"|"cancelled"} status
   * @property {string}  professionSlug   Categoria profissional predominante.
   * @property {string}  timezone
   *
   * @typedef {Object} Membership      Vínculo usuário <-> tenant. É o que dá acesso.
   * @property {string}  id
   * @property {string}  userId
   * @property {string}  tenantId
   * @property {Role}    role
   * @property {"all"|"own"} dataScope        Alcance dos dados dentro do tenant.
   * @property {string[]} permissions         Efetivas: papel + concessões - revogações.
   * @property {string|null} professionalId   Nulo para quem não atende (recepção).
   * @property {"invited"|"active"|"suspended"} status
   *
   * @typedef {"OWNER"|"PROFESSIONAL"|"ASSISTANT"} Role
   *
   * @typedef {Object} Professional    Perfil profissional dentro de um tenant.
   * @property {string}  id
   * @property {string}  tenantId
   * @property {string|null} membershipId
   * @property {string}  professionSlug
   * @property {string}  displayName
   * @property {string|null} council           "CRP", "CREFITO"… quando a profissão exigir.
   * @property {string|null} registrationNumber
   * @property {string[]} specialties
   * @property {string[]} modalities
   * @property {Object}  customFields          Campos definidos pela profissão.
   *
   * @typedef {Object} Client          Pessoa atendida. Rótulo na tela vem de terms.
   * @property {string}  id
   * @property {string}  tenantId
   * @property {string}  name
   * @property {string|null} email
   * @property {string|null} phone
   * @property {"active"|"inactive"|"archived"} status
   *
   * @typedef {Object} Appointment
   * @property {string}  id
   * @property {string}  tenantId
   * @property {string}  clientId
   * @property {string}  professionalId
   * @property {string}  inicio                ISO 8601, UTC.
   * @property {number}  duracaoMin
   * @property {"presencial"|"online"} modalidade
   * @property {"agendado"|"confirmado"|"realizado"|"falta"|"cancelado"} status
   * @property {"pago"|"pendente"|"isento"} pagamento
   * @property {number}  valor
   *
   * @typedef {Object} ClinicalRecord  Conteúdo protegido: nunca entra em listagem.
   * @property {string}  id
   * @property {string}  tenantId
   * @property {string}  clientId
   * @property {string}  authorProfessionalId
   * @property {"session"|"evolution"|"assessment"|"referral"} kind
   * @property {string}  createdAt
   *
   * @typedef {Object} AuditLog
   * @property {string}  id
   * @property {string|null} tenantId
   * @property {"user"|"platform"|"system"} actorType
   * @property {string}  action
   * @property {string}  entity
   * @property {string}  entityId
   * @property {string}  createdAt
   */

  /* ---------------- Papéis ---------------- */
  var ROLES = {
    OWNER: "OWNER",                 // administra a conta — não implica acesso clínico
    PROFESSIONAL: "PROFESSIONAL",   // atende: agenda, clientes e registros próprios
    ASSISTANT: "ASSISTANT"          // apoio administrativo, sem conteúdo clínico
  };

  var SCOPES = { ALL: "all", OWN: "own" };

  /* ---------------- Permissões ----------------
     Nome no formato recurso.ação. Esta lista é o contrato com o
     backend: o servidor decide, o front apenas esconde o que a
     pessoa não pode usar. */
  var PERMISSIONS = {
    AGENDA_READ: "agenda.read",
    AGENDA_WRITE: "agenda.write",
    AGENDA_MANAGE_OTHERS: "agenda.manage_others",

    PATIENTS_READ: "patients.read",
    PATIENTS_WRITE: "patients.write",
    PATIENTS_ARCHIVE: "patients.archive",

    APPOINTMENTS_READ: "appointments.read",
    APPOINTMENTS_WRITE: "appointments.write",
    APPOINTMENTS_CANCEL: "appointments.cancel",

    FINANCE_READ: "finance.read",
    FINANCE_WRITE: "finance.write",
    FINANCE_EXPORT: "finance.export",

    CLINICAL_RECORDS_READ: "clinical_records.read",
    CLINICAL_RECORDS_WRITE: "clinical_records.write",
    CLINICAL_RECORDS_READ_OTHERS: "clinical_records.read_others",

    DOCUMENTS_READ: "documents.read",
    DOCUMENTS_WRITE: "documents.write",

    MEMBERS_MANAGE: "members.manage",
    SETTINGS_MANAGE: "settings.manage",
    AUDIT_READ: "audit.read",
    DATA_REQUESTS_MANAGE: "data_requests.manage"
  };

  /* ---------------- Classificação do dado ----------------
     Separação exigida pela Etapa 2: administrar a conta não dá
     acesso ao conteúdo clínico. Vale como referência única para
     front, backend e documentação. */
  var DATA_CLASS = {
    ADMINISTRATIVE: "administrative",  // cadastro, contato, agenda, presença, falta, pagamento
    CLINICAL: "clinical",              // registro clínico, evolução, observação clínica, documento clínico
    ACCOUNT: "account",                // usuários, plano, configurações do tenant
    AUDIT: "audit"                     // trilha de acesso
  };

  /* Quais permissões alcançam cada classe. Nenhuma permissão
     administrativa abre conteúdo clínico — nem a de OWNER. */
  var CLASS_PERMISSIONS = {
    administrative: [
      PERMISSIONS.AGENDA_READ, PERMISSIONS.AGENDA_WRITE, PERMISSIONS.AGENDA_MANAGE_OTHERS,
      PERMISSIONS.PATIENTS_READ, PERMISSIONS.PATIENTS_WRITE, PERMISSIONS.PATIENTS_ARCHIVE,
      PERMISSIONS.APPOINTMENTS_READ, PERMISSIONS.APPOINTMENTS_WRITE, PERMISSIONS.APPOINTMENTS_CANCEL,
      PERMISSIONS.FINANCE_READ, PERMISSIONS.FINANCE_WRITE, PERMISSIONS.FINANCE_EXPORT
    ],
    clinical: [
      PERMISSIONS.CLINICAL_RECORDS_READ, PERMISSIONS.CLINICAL_RECORDS_WRITE, PERMISSIONS.CLINICAL_RECORDS_READ_OTHERS,
      PERMISSIONS.DOCUMENTS_READ, PERMISSIONS.DOCUMENTS_WRITE
    ],
    account: [PERMISSIONS.MEMBERS_MANAGE, PERMISSIONS.SETTINGS_MANAGE, PERMISSIONS.DATA_REQUESTS_MANAGE],
    audit: [PERMISSIONS.AUDIT_READ]
  };

  /* Matriz padrão. O servidor é a autoridade; isto espelha o seed
     para o front saber o que desenhar antes de a sessão responder. */
  var ROLE_PERMISSIONS = {
    OWNER: [
      PERMISSIONS.AGENDA_READ, PERMISSIONS.AGENDA_WRITE, PERMISSIONS.AGENDA_MANAGE_OTHERS,
      PERMISSIONS.PATIENTS_READ, PERMISSIONS.PATIENTS_WRITE, PERMISSIONS.PATIENTS_ARCHIVE,
      PERMISSIONS.APPOINTMENTS_READ, PERMISSIONS.APPOINTMENTS_WRITE, PERMISSIONS.APPOINTMENTS_CANCEL,
      PERMISSIONS.FINANCE_READ, PERMISSIONS.FINANCE_WRITE, PERMISSIONS.FINANCE_EXPORT,
      PERMISSIONS.MEMBERS_MANAGE, PERMISSIONS.SETTINGS_MANAGE, PERMISSIONS.AUDIT_READ,
      PERMISSIONS.DATA_REQUESTS_MANAGE
      /* Sem CLINICAL_*: administrar a conta não abre prontuário alheio.
         Se o dono também atender, ele tem uma membership PROFESSIONAL
         (ou as permissões clínicas concedidas explicitamente). */
    ],
    PROFESSIONAL: [
      PERMISSIONS.AGENDA_READ, PERMISSIONS.AGENDA_WRITE,
      PERMISSIONS.PATIENTS_READ, PERMISSIONS.PATIENTS_WRITE,
      PERMISSIONS.APPOINTMENTS_READ, PERMISSIONS.APPOINTMENTS_WRITE, PERMISSIONS.APPOINTMENTS_CANCEL,
      PERMISSIONS.FINANCE_READ,
      PERMISSIONS.CLINICAL_RECORDS_READ, PERMISSIONS.CLINICAL_RECORDS_WRITE,
      PERMISSIONS.DOCUMENTS_READ, PERMISSIONS.DOCUMENTS_WRITE
      /* Sem CLINICAL_READ_OTHERS: só o que é dele. */
    ],
    ASSISTANT: [
      PERMISSIONS.AGENDA_READ, PERMISSIONS.AGENDA_WRITE, PERMISSIONS.AGENDA_MANAGE_OTHERS,
      PERMISSIONS.PATIENTS_READ, PERMISSIONS.PATIENTS_WRITE,
      PERMISSIONS.APPOINTMENTS_READ, PERMISSIONS.APPOINTMENTS_WRITE, PERMISSIONS.APPOINTMENTS_CANCEL,
      PERMISSIONS.FINANCE_READ, PERMISSIONS.FINANCE_WRITE
      /* Nunca CLINICAL_* nem DOCUMENT_*. */
    ]
  };

  function ehClinica(permissao) {
    return CLASS_PERMISSIONS.clinical.indexOf(permissao) > -1;
  }

  VC.types = {
    ROLES: ROLES,
    SCOPES: SCOPES,
    PERMISSIONS: PERMISSIONS,
    ROLE_PERMISSIONS: ROLE_PERMISSIONS,
    DATA_CLASS: DATA_CLASS,
    CLASS_PERMISSIONS: CLASS_PERMISSIONS,
    ehClinica: ehClinica
  };
})(window);
