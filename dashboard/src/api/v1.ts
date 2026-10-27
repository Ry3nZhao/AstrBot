import type { AxiosRequestConfig, AxiosResponse } from 'axios';

import * as openApiV1 from './generated/openapi-v1';
import {
  client as openApiV1Client,
  type BotConfigRequest,
  type BotCleanupTarget,
  type BotRegistrationRequest,
  type CommandPatchRequest,
  type ConfigRouteUpsertRequest,
  type ConfigRoutesReplaceRequest,
  type CreateApiKeyRequest,
  type DynamicConfig,
  type EnabledPatch,
  type GhproxyTestRequest,
  type LoginRequest,
  type PipInstallRequest,
  type PluginVersionSupportRequest,
  type PluginValidateRepoRequest,
  type PluginConfigFileDeleteRequest,
  type RuntimeInfo,
  type BatchSessionServiceRequest,
  type SetupAuthRequest,
  type SessionGroupRequest,
  type SessionRuleRequest,
  type UmoListRequest,
  type T2iTemplateRequest,
  type TotpSetupRequest,
  type TraceSettingsRequest,
  type UpdateAccountRequest,
  type UpdateRequest,
} from './generated/openapi-v1';
import { apiV1Client, fetchWithAuth, httpClient } from './http';

openApiV1Client.setConfig({
  axios: httpClient,
  throwOnError: true,
});

export interface ApiEnvelope<T> {
  status: 'ok' | 'error';
  message?: string | null;
  data: T;
}

export const UPGRADE_RECOVERY_EVENT = 'astrbot-upgrade-recovery';
export const UPGRADE_RECOVERY_TOKEN_KEY = 'astrbot-upgrade-recovery-token';

export type OpenConfig = DynamicConfig;

export interface VersionData {
  version?: string;
  dashboard_version?: string;
  change_pwd_hint?: boolean;
  md5_pwd_hint?: boolean;
  password_upgrade_required?: boolean;
  runtime?: RuntimeInfo;
  [key: string]: unknown;
}

export interface PublicVersionData {
  webui_version?: string | null;
  astrbot_version?: string | null;
  astrbot_code_version?: string | null;
  [key: string]: unknown;
}

type StartTimeData = {
  start_time?: number | string | null;
};

export interface CommandListData {
  items?: any[];
  wake_prefix?: string[];
  summary?: {
    disabled?: number;
    conflicts?: number;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface BotListParams {
  enabled?: boolean;
  type?: string;
}

export interface SessionListParams {
  page?: number;
  page_size?: number;
  search?: string;
  platform?: string;
  message_type?: 'all' | 'group' | 'private';
}

export interface SessionRuleListParams {
  page?: number;
  page_size?: number;
  search?: string;
}

type V1Response<T> = Promise<
  AxiosResponse<ApiEnvelope<T>> & { legacyFallback?: boolean }
>;

function typed<T>(response: Promise<unknown>): V1Response<T> {
  return response as unknown as V1Response<T>;
}

export function isLegacyFallbackError(error: unknown): boolean {
  const axiosError = error as {
    response?: { status?: number; data?: { message?: string } | string };
    message?: string;
  };
  if (axiosError.response?.status === 404) {
    return true;
  }

  const data = axiosError.response?.data;
  const message =
    typeof data === 'string' ? data : data?.message || axiosError.message || '';
  return message.toLowerCase().includes('missing api key');
}

function withLegacyFallback<T>(
  primary: Promise<unknown>,
  legacy: () => Promise<AxiosResponse<ApiEnvelope<T>>>,
): V1Response<T> {
  const legacyRequest = () =>
    legacy().then((response) => {
      const legacyResponse = response as AxiosResponse<ApiEnvelope<T>> & {
        legacyFallback?: boolean;
      };
      legacyResponse.legacyFallback = true;
      return legacyResponse;
    });

  return typed<T>(primary).then((response) => {
    const message = response.data?.message || '';
    if (
      response.data?.status === 'error' &&
      message.toLowerCase().includes('missing api key')
    ) {
      return legacyRequest();
    }
    return response;
  }).catch((error) => {
    if (isLegacyFallbackError(error)) {
      return legacyRequest();
    }
    throw error;
  });
}

function firstSuccessfulResponse<T>(
  requests: Array<Promise<AxiosResponse<ApiEnvelope<T>>>>,
): V1Response<T> {
  return new Promise<AxiosResponse<ApiEnvelope<T>>>((resolve, reject) => {
    let pending = requests.length;
    let firstError: unknown;
    requests.forEach((request) => {
      request.then(resolve).catch((error) => {
        if (firstError === undefined) {
          firstError = error;
        }
        pending -= 1;
        if (pending === 0) {
          reject(firstError);
        }
      });
    });
  });
}

function generatedOptions(
  options: Record<string, unknown>,
  requestConfig?: AxiosRequestConfig,
) {
  return { ...options, ...(requestConfig || {}) } as any;
}

function generatedQuery<T extends object>(
  params?: T,
): (T & Record<string, unknown>) | undefined {
  return params as (T & Record<string, unknown>) | undefined;
}

function generatedFormData(formData: FormData | Record<string, unknown>) {
  if (typeof FormData !== 'undefined' && formData instanceof FormData) {
    const body: Record<string, unknown> = {};
    formData.forEach((value, key) => {
      const existing = body[key];
      if (existing === undefined) {
        body[key] = value;
      } else if (Array.isArray(existing)) {
        existing.push(value);
      } else {
        body[key] = [existing, value];
      }
    });
    return body as any;
  }
  return formData as any;
}

function botConfig(config: OpenConfig): BotConfigRequest {
  return {
    id: typeof config.id === 'string' ? config.id : undefined,
    type: typeof config.type === 'string' ? config.type : '',
    enabled:
      typeof config.enable === 'boolean'
        ? config.enable
        : typeof config.enabled === 'boolean'
          ? config.enabled
          : undefined,
    config,
  };
}

function pluginExtensionPath(pluginPath: string): string {
  return pluginPath
    .replace(/^\/+/, '')
    .split('/')
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join('/');
}

export const configProfileApi = {
  schema() {
    return typed<OpenConfig>(openApiV1.getConfigProfileSchema());
  },
  list() {
    return typed<{ info_list: OpenConfig[] }>(openApiV1.listConfigProfiles());
  },
  create(payload: { name?: string | null; config?: OpenConfig | null }) {
    return typed<{ conf_id: string }>(
      openApiV1.createConfigProfile({
        body: {
          name: payload.name ?? undefined,
          config: payload.config ?? undefined,
        },
      }),
    );
  },
  get(configId: string) {
    return typed<OpenConfig>(
      openApiV1.getConfigProfile({ path: { config_id: configId } }),
    );
  },
  update(
    configId: string,
    config: OpenConfig,
    requestConfig?: AxiosRequestConfig,
  ) {
    return typed<OpenConfig>(
      openApiV1.updateConfigProfileContent(
        generatedOptions(
          {
            path: { config_id: configId },
            body: config,
          },
          requestConfig,
        ),
      ),
    );
  },
  rename(configId: string, name: string | null) {
    return typed<OpenConfig>(
      openApiV1.renameConfigProfile({
        path: { config_id: configId },
        body: { name: name ?? '' },
      }),
    );
  },
  delete(configId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteConfigProfile({ path: { config_id: configId } }),
    );
  },
};

export const systemConfigApi = {
  schema() {
    return typed<OpenConfig>(openApiV1.getSystemConfigSchema());
  },
  get() {
    return typed<OpenConfig>(openApiV1.getSystemConfig());
  },
  runtime() {
    return typed<OpenConfig>(openApiV1.getSystemConfigRuntime());
  },
  update(config: OpenConfig, requestConfig?: AxiosRequestConfig) {
    return typed<OpenConfig>(
      openApiV1.updateSystemConfig(
        generatedOptions({ body: config }, requestConfig),
      ),
    );
  },
};

export const configRouteApi = {
  list() {
    return typed<{ routing?: Record<string, string> }>(openApiV1.listConfigRoutes());
  },
  replace(payload: ConfigRoutesReplaceRequest) {
    return typed<OpenConfig>(openApiV1.replaceConfigRoutes({ body: payload }));
  },
  upsert(umo: string, payload: ConfigRouteUpsertRequest) {
    return typed<OpenConfig>(
      openApiV1.upsertConfigRoute({ path: { umo }, body: payload }),
    );
  },
  delete(umo: string) {
    return typed<OpenConfig>(
      openApiV1.deleteConfigRoute({ path: { umo } }),
    );
  },
};

export const botApi = {
  types() {
    return typed<{ bot_types: OpenConfig[] }>(openApiV1.listBotTypes());
  },
  list(params?: BotListParams) {
    return typed<{ bots: OpenConfig[] }>(
      openApiV1.listBots({ query: generatedQuery(params) }),
    );
  },
  stats() {
    return typed<{ platforms: OpenConfig[] }>(openApiV1.listBotStats());
  },
  registration(botType: string, payload: BotRegistrationRequest) {
    return typed<any>(
      openApiV1.registerBotType({
        path: { bot_type: botType },
        body: payload,
      }),
    );
  },
  create(config: OpenConfig) {
    return typed<OpenConfig>(openApiV1.createBot({ body: botConfig(config) }));
  },
  get(botId: string) {
    return typed<{ bot: OpenConfig }>(
      openApiV1.getBotById({ query: { bot_id: botId } }),
    );
  },
  update(botId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updateBotById({
        body: { bot_id: botId, config },
      }),
    );
  },
  setEnabled(botId: string, payload: EnabledPatch) {
    return typed<OpenConfig>(
      openApiV1.setBotEnabledById({
        body: { bot_id: botId, enabled: payload.enabled },
      }),
    );
  },
  delete(botId: string, cleanup: BotCleanupTarget[] = []) {
    return typed<OpenConfig>(
      openApiV1.deleteBotById({
        query: { bot_id: botId, cleanup },
        paramsSerializer: { indexes: null },
      }),
    );
  },
};

export const authApi = {
  login(payload: LoginRequest) {
    return withLegacyFallback<any>(openApiV1.login({ body: payload }), () =>
      httpClient.post<ApiEnvelope<any>>('/api/auth/login', payload),
    );
  },
  logout() {
    return withLegacyFallback<OpenConfig>(openApiV1.logout(), () =>
      httpClient.post<ApiEnvelope<OpenConfig>>('/api/auth/logout'),
    );
  },
  setupStatus() {
    return withLegacyFallback<any>(openApiV1.getAuthSetupStatus(), () =>
      httpClient.get<ApiEnvelope<any>>('/api/auth/setup-status'),
    );
  },
  setup(payload: SetupAuthRequest) {
    return withLegacyFallback<OpenConfig>(openApiV1.setupAuth({ body: payload }), () =>
      httpClient.post<ApiEnvelope<OpenConfig>>('/api/auth/setup', payload),
    );
  },
  setupTotp(payload?: TotpSetupRequest) {
    return withLegacyFallback<any>(openApiV1.setupTotp({ body: payload }), () =>
      httpClient.post<ApiEnvelope<any>>('/api/auth/totp/setup', payload),
    );
  },
  recoverTotp() {
    return withLegacyFallback<any>(openApiV1.recoverTotp(), () =>
      httpClient.post<ApiEnvelope<any>>('/api/auth/totp/recovery'),
    );
  },
  updateAccount(payload: UpdateAccountRequest) {
    return withLegacyFallback<OpenConfig>(
      openApiV1.updateAuthAccount({ body: payload }),
      () => httpClient.post<ApiEnvelope<OpenConfig>>('/api/auth/account/edit', payload),
    );
  },
};

export const apiKeyApi = {
  list() {
    return typed<OpenConfig[]>(openApiV1.listApiKeys());
  },
  create(payload: CreateApiKeyRequest) {
    return typed<{ api_key?: string }>(openApiV1.createApiKey({ body: payload }));
  },
  revoke(keyId: string) {
    return typed<OpenConfig>(
      openApiV1.revokeApiKey({ path: { key_id: keyId } }),
    );
  },
  delete(keyId: string) {
    return typed<OpenConfig>(
      openApiV1.deleteApiKey({ path: { key_id: keyId } }),
    );
  },
};

export const traceApi = {
  history(query?: { limit?: number; page?: number; cursor?: string; query?: string; errors?: boolean; models?: boolean; plugins?: boolean }) {
    return typed<OpenConfig>(openApiV1.listTraces({ query }));
  },
  detail(traceId: string) {
    return typed<OpenConfig>(openApiV1.getTraceDetail({ path: { trace_id: traceId } }));
  },
  getSettings() {
    return typed<OpenConfig>(openApiV1.getTraceSettings());
  },
  updateSettings(settings: TraceSettingsRequest) {
    return typed<OpenConfig>(
      openApiV1.updateTraceSettings({ body: settings }),
    );
  },
};

export const updatesApi = {
  check() {
    return withLegacyFallback<any>(openApiV1.checkUpdate(), () =>
      httpClient.get<ApiEnvelope<any>>('/api/update/check'),
    );
  },
  releases(type?: 'core' | 'dashboard') {
    return withLegacyFallback<any[]>(
      openApiV1.listReleases({
        query: type ? { type } : undefined,
      }),
      () =>
        httpClient.get<ApiEnvelope<any[]>>('/api/update/releases', {
          params: type ? { type } : undefined,
        }),
    );
  },
  core(payload?: UpdateRequest) {
    return withLegacyFallback<OpenConfig>(openApiV1.updateCore({ body: payload }), () =>
      httpClient.post<ApiEnvelope<OpenConfig>>('/api/update/do', payload),
    );
  },
  dashboard(payload?: UpdateRequest) {
    return withLegacyFallback<OpenConfig>(
      openApiV1.updateDashboard({ body: payload }),
      () => httpClient.post<ApiEnvelope<OpenConfig>>('/api/update/dashboard', payload),
    );
  },
  progress(taskId: string) {
    return withLegacyFallback<any>(
      openApiV1.getUpdateProgress({ path: { task_id: taskId } }),
      () =>
        httpClient.get<ApiEnvelope<any>>('/api/update/progress', {
          params: { id: taskId },
        }),
    );
  },
  installPip(payload: PipInstallRequest) {
    return withLegacyFallback<OpenConfig>(
      openApiV1.installPipPackage({ body: payload }),
      () => httpClient.post<ApiEnvelope<OpenConfig>>('/api/update/pip-install', payload),
    );
  },
};

export const fileApi = {
  tokenUrl(fileToken: string) {
    return `/api/v1/files/tokens/${encodeURIComponent(fileToken)}`;
  },
};

export const sessionApi = {
  senders(params?: { search?: string; limit?: number; page?: number; sender_ids?: string[] }) {
    return typed<{ page: number; has_more: boolean; senders: Array<{
      umo: string;
      sender_id: string;
      sender_name: string;
      platform: string;
      display_name: string;
    }> }>(openApiV1.listSessionSenders({ query: params }));
  },
  list(params?: SessionListParams) {
    return typed<any>(openApiV1.listSessions({ query: generatedQuery(params) }));
  },
  activeUmos(params?: { platform_id?: string }) {
    return typed<any>(openApiV1.listActiveUmos({ query: params }));
  },
  listRules(params?: SessionRuleListParams) {
    return typed<any>(
      openApiV1.listSessionRules({ query: generatedQuery(params) }),
    );
  },
  upsertRule(payload: SessionRuleRequest) {
    return typed<any>(openApiV1.upsertSessionRule({ body: payload }));
  },
  deleteRules(payload: UmoListRequest) {
    return typed<any>(openApiV1.deleteSessionRules({ body: payload }));
  },
  batchUpdateService(payload: BatchSessionServiceRequest) {
    return typed<any>(
      openApiV1.batchUpdateSessionService({ body: payload }),
    );
  },
  listGroups() {
    return typed<any>(openApiV1.listSessionGroups());
  },
  createGroup(payload: SessionGroupRequest) {
    return typed<any>(openApiV1.createSessionGroup({ body: payload }));
  },
  updateGroup(groupId: string, payload: SessionGroupRequest) {
    return typed<any>(
      openApiV1.updateSessionGroup({
        path: { group_id: groupId },
        body: payload,
      }),
    );
  },
  deleteGroup(groupId: string) {
    return typed<any>(
      openApiV1.deleteSessionGroup({ path: { group_id: groupId } }),
    );
  },
};

export const commandApi = {
  list(configId?: string) {
    return typed<CommandListData>(
      openApiV1.listCommands({
        query: configId ? { config_id: configId } : undefined,
      }),
    );
  },
  conflicts() {
    return typed<OpenConfig>(openApiV1.listCommandConflicts());
  },
  update(commandId: string, patch: CommandPatchRequest) {
    return typed<OpenConfig>(
      openApiV1.updateCommand({
        path: { command_id: commandId },
        body: patch,
      }),
    );
  },
};

export const t2iApi = {
  listTemplates() {
    return typed<OpenConfig[]>(openApiV1.listT2iTemplates());
  },
  getTemplate(name: string) {
    return typed<{ name: string; content: string }>(
      openApiV1.getT2iTemplate({ path: { name } }),
    );
  },
  createTemplate(payload: T2iTemplateRequest) {
    return typed<OpenConfig>(
      openApiV1.createT2iTemplate({ body: payload }),
    );
  },
  updateTemplate(name: string, content: string) {
    return typed<OpenConfig>(
      openApiV1.updateT2iTemplate({
        path: { name },
        body: { content },
      }),
    );
  },
  deleteTemplate(name: string) {
    return typed<OpenConfig>(
      openApiV1.deleteT2iTemplate({ path: { name } }),
    );
  },
  getActiveTemplate() {
    return typed<{ active_template?: string }>(openApiV1.getActiveT2iTemplate());
  },
  setActiveTemplate(name: string) {
    return typed<OpenConfig>(
      openApiV1.setActiveT2iTemplate({ body: { name } }),
    );
  },
  resetDefaultTemplate() {
    return typed<OpenConfig>(openApiV1.resetDefaultT2iTemplate());
  },
};

export const logApi = {
  history() {
    return typed<{ logs?: OpenConfig[] }>(openApiV1.getLogHistory());
  },
  exportArchive(redact = true, startTime?: number, endTime?: number) {
    return openApiV1.exportLogs({
      query: { redact, start_time: startTime, end_time: endTime },
      responseType: 'blob',
    }) as Promise<AxiosResponse<Blob>>;
  },
  liveUrl() {
    return '/api/v1/logs/live';
  },
};

export const pluginApi = {
  list(params?: { include_reserved?: boolean; enabled?: boolean }) {
    return typed<any[]>(openApiV1.listPlugins({ query: params }));
  },
  get(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPluginById({ query: { plugin_id: pluginId } }),
    );
  },
  failed() {
    return typed<Record<string, OpenConfig>>(openApiV1.listFailedPlugins());
  },
  reloadFailed(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.reloadFailedPlugin({ path: { plugin_id: pluginId } }),
    );
  },
  uninstallFailed(
    pluginId: string,
    options?: { delete_config?: boolean; delete_data?: boolean },
  ) {
    return typed<OpenConfig>(
      openApiV1.uninstallFailedPlugin({
        path: { plugin_id: pluginId },
        body: options,
      }),
    );
  },
  uninstall(
    pluginId: string,
    options?: { delete_config?: boolean; delete_data?: boolean },
  ) {
    return typed<OpenConfig>(
      openApiV1.uninstallPluginById({
        query: { plugin_id: pluginId },
        body: options,
      }),
    );
  },
  reload(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.reloadPluginById({ body: { plugin_id: pluginId } }),
    );
  },
  setEnabled(pluginId: string, enabled: boolean) {
    return typed<OpenConfig>(
      openApiV1.setPluginEnabledById({
        body: { plugin_id: pluginId, enabled },
      }),
    );
  },
  update(pluginId: string, body?: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updatePlugins({
        body: { plugin_id: pluginId, ...(body || {}) } as any,
      }),
    );
  },
  updateMany(body: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updatePlugins({ body: body as any }),
    );
  },
  checkVersionSupport(payload: PluginVersionSupportRequest) {
    return typed<any>(
      openApiV1.checkPluginVersionSupport({ body: payload }),
    );
  },
  config(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPluginConfigById({ query: { plugin_id: pluginId } }),
    );
  },
  updateConfig(pluginId: string, config: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.updatePluginConfigById({
        body: { plugin_id: pluginId, config },
      }),
    );
  },
  updateLogLevel(
    pluginId: string,
    level: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL" | null,
  ) {
    return typed<OpenConfig>(
      openApiV1.updatePluginLogLevel({
        path: { plugin_id: pluginId },
        body: { level },
      }),
    );
  },
  listConfigFiles(pluginId: string, configKey: string) {
    return typed<any>(
      openApiV1.listPluginConfigFilesById({
        query: { plugin_id: pluginId, config_key: configKey },
      }),
    );
  },
  uploadConfigFiles(pluginId: string, configKey: string, formData: FormData) {
    return typed<any>(
      openApiV1.uploadPluginConfigFilesById({
        query: { plugin_id: pluginId, config_key: configKey },
        body: generatedFormData(formData),
      }),
    );
  },
  deleteConfigFile(pluginId: string, payload: PluginConfigFileDeleteRequest) {
    return typed<OpenConfig>(
      openApiV1.deletePluginConfigFileById({
        query: { plugin_id: pluginId },
        body: payload,
      }),
    );
  },
  readme(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPluginReadmeById({ query: { plugin_id: pluginId } }),
    );
  },
  changelog(pluginId: string) {
    return typed<OpenConfig>(
      openApiV1.getPluginChangelogById({ query: { plugin_id: pluginId } }),
    );
  },
  market(params?: {
    page?: number;
    page_size?: number;
    category?: string;
    sort?: 'recommended' | 'downloads' | 'updated' | 'name';
    keyword?: string;
    force_refresh?: boolean;
    custom_registry?: string;
  }) {
    return typed<any>(openApiV1.listPluginMarket({ query: params }));
  },
  sources() {
    return typed<any>(openApiV1.listPluginSources());
  },
  replaceSources(sources: OpenConfig[]) {
    return typed<OpenConfig>(
      openApiV1.replacePluginSources({ body: { sources: sources as any } }),
    );
  },
  async installUpload(formData: FormData) {
    const response = await fetchWithAuth('/api/v1/plugins/install/upload', {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(
        data?.message || `Plugin upload failed (${response.status})`,
      );
    }
    return { data } as AxiosResponse<ApiEnvelope<OpenConfig>>;
  },
  installGithub(body: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.installPluginFromGithub({ body: body as any }),
    );
  },
  installGit(body: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.installPluginFromGit({ body: body as any }),
    );
  },
  installUrl(body: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.installPluginFromUrl({ body: body as any }),
    );
  },
  validateRepo(body: PluginValidateRepoRequest) {
    return typed<OpenConfig>(
      openApiV1.validatePluginRepo({ body }),
    );
  },
  bindSource(pluginId: string, body: OpenConfig) {
    return typed<OpenConfig>(
      openApiV1.bindPluginSource({
        path: { plugin_id: pluginId },
        body: body as any,
      }),
    );
  },
  page(pluginId: string, pageName: string) {
    return typed<any>(
      openApiV1.getPluginViewById({
        query: { plugin_id: pluginId, page_name: pageName },
      }) as any,
    );
  },
};

export const pluginExtensionApi = {
  get<T = any>(pluginPath: string, config?: AxiosRequestConfig) {
    return apiV1Client.get<ApiEnvelope<T>>(
      `/plugins/extensions/${pluginExtensionPath(pluginPath)}`,
      config,
    );
  },
  post<T = any>(
    pluginPath: string,
    data?: unknown,
    config?: AxiosRequestConfig,
  ) {
    return apiV1Client.post<ApiEnvelope<T>>(
      `/plugins/extensions/${pluginExtensionPath(pluginPath)}`,
      data,
      config,
    );
  },
  put<T = any>(pluginPath: string, data?: unknown, config?: AxiosRequestConfig) {
    return apiV1Client.put<ApiEnvelope<T>>(
      `/plugins/extensions/${pluginExtensionPath(pluginPath)}`,
      data,
      config,
    );
  },
  patch<T = any>(pluginPath: string, data?: unknown, config?: AxiosRequestConfig) {
    return apiV1Client.patch<ApiEnvelope<T>>(
      `/plugins/extensions/${pluginExtensionPath(pluginPath)}`,
      data,
      config,
    );
  },
  delete<T = any>(pluginPath: string, config?: AxiosRequestConfig) {
    return apiV1Client.delete<ApiEnvelope<T>>(
      `/plugins/extensions/${pluginExtensionPath(pluginPath)}`,
      config,
    );
  },
};

export const statsApi = {
  get(offsetSec?: number) {
    return typed<any>(
      openApiV1.getStats({
        query: offsetSec === undefined ? undefined : { offset_sec: offsetSec },
      }),
    );
  },
  providerTokens(days?: number) {
    return typed<any>(
      openApiV1.getProviderTokenStats({
        query: days === undefined ? undefined : { days },
      }),
    );
  },
  version() {
    return withLegacyFallback<VersionData>(openApiV1.getVersion(), () =>
      httpClient.get<ApiEnvelope<VersionData>>('/api/stat/version'),
    );
  },
  firstNotice(locale?: string) {
    return typed<{ content?: string | null }>(
      openApiV1.getFirstNotice({
        query: locale ? { locale } : undefined,
      }),
    );
  },
  testGhproxy(payload: GhproxyTestRequest) {
    return withLegacyFallback<{ latency?: number }>(
      openApiV1.testGhproxyConnection({ body: payload }),
      () =>
        httpClient.post<ApiEnvelope<{ latency?: number }>>(
          '/api/stat/test-ghproxy-connection',
          payload,
        ),
    );
  },
  startTime() {
    const v1Request = typed<StartTimeData>(openApiV1.getStartTime());
    const legacyRequest = httpClient.get<ApiEnvelope<StartTimeData>>(
      '/api/stat/start-time',
    );

    // Restart polling must also work after downgrading to backends without v1 stats routes.
    return firstSuccessfulResponse<StartTimeData>([v1Request, legacyRequest]);
  },
  restart() {
    return withLegacyFallback<OpenConfig>(openApiV1.restartCore(), () =>
      httpClient.post<ApiEnvelope<OpenConfig>>('/api/stat/restart-core'),
    );
  },
  storage() {
    return typed<OpenConfig>(openApiV1.getStorageStatus());
  },
  cleanupStorage(target: 'logs' | 'cache' | 'traces' | 'all' = 'all') {
    return typed<OpenConfig>(
      openApiV1.cleanupStorage({
        body: target ? { target } : undefined,
      }),
    );
  },
};

export const publicApi = {
  versions() {
    return withLegacyFallback<PublicVersionData>(
      openApiV1.getPublicVersions(),
      () => httpClient.get<ApiEnvelope<PublicVersionData>>('/api/stat/versions'),
    );
  },
};

export const changelogApi = {
  listVersions() {
    return typed<{ versions?: string[] }>(openApiV1.listChangelogVersions());
  },
  get(version: string) {
    return typed<{ content?: string }>(
      openApiV1.getChangelog({ path: { version } }),
    );
  },
};
