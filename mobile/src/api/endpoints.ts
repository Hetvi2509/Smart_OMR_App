import { Platform } from 'react-native';

import { api, getBaseUrl, getToken, request } from './client';
import {
  AnswerKeyEntry, AuthResponse, Candidate, DashboardData, Health, HistoryRow,
  LayoutInfo, ReportMeta, ResultDetail, ScanResponse, Test, TestResultsResponse,
} from './types';

export const endpoints = {
  health: () => api.get<Health>('/health'),
  layouts: () => api.get<{ layouts: LayoutInfo[] }>('/layouts'),

  signup: (body: {
    email: string; password: string; full_name: string;
    institution_name?: string | null;
  }) => api.post<AuthResponse>('/auth/signup', body),
  login: (body: { email: string; password: string }) =>
    api.post<AuthResponse>('/auth/login', body),
  me: () => api.get<{ user: AuthResponse['user'] }>('/auth/me'),

  dashboard: () => api.get<DashboardData>('/dashboard'),

  listTests: (q?: string) =>
    api.get<{ tests: Test[] }>(`/tests${q ? `?q=${encodeURIComponent(q)}` : ''}`),
  getTest: (id: number) => api.get<{ test: Test }>(`/tests/${id}`),
  createTest: (body: Partial<Test>) => api.post<{ test: Test }>('/tests', body),
  updateTest: (id: number, body: Partial<Test>) =>
    api.put<{ test: Test }>(`/tests/${id}`, body),
  deleteTest: (id: number) => api.del<{ deleted: boolean }>(`/tests/${id}`),

  getAnswerKey: (testId: number) =>
    api.get<{ test_id: number; total_questions: number; entries: AnswerKeyEntry[]; count: number }>(
      `/tests/${testId}/answer-key`),
  putAnswerKey: (testId: number, entries: AnswerKeyEntry[]) =>
    api.put<{ test_id: number; count: number }>(`/tests/${testId}/answer-key`, { entries }),

  /** Upload one sheet. `uri` is a local file URI from the camera or picker. */
  /** Upload one sheet. `uri` is a local file URI from the camera or picker.
   *
   *  The two platforms need different FormData payloads and there is no
   *  shape that works on both: React Native's FormData takes a
   *  {uri, name, type} descriptor and streams the file itself, while on web
   *  that object serialises to the string "[object Object]" and the server
   *  rejects it ("Expected UploadFile, received: str"). Web therefore has to
   *  fetch the URI into a real Blob first.
   */
  scan: async (
    testId: number,
    file: { uri: string; name: string; type: string },
  ) => {
    const form = new FormData();

    if (Platform.OS === 'web') {
      const blob = await (await fetch(file.uri)).blob();
      form.append('file', new File([blob], file.name, {
        type: blob.type || file.type,
      }));
    } else {
      if (!file.uri) {
        throw new Error('The prepared image has no file path to upload.');
      }
      // A fresh plain object with exactly the three keys React Native's
      // FormData understands. Passing the prepared object through directly
      // risks handing the native encoder something it cannot read, which it
      // reports only as "Unsupported FormData part implementation".
      form.append('file', {
        uri: String(file.uri),
        name: String(file.name || 'sheet.jpg'),
        type: String(file.type || 'image/jpeg'),
      } as unknown as Blob);
    }
    return api.upload<ScanResponse>(`/tests/${testId}/scan`, form);
  },

  listResults: (params: {
    q?: string; test_id?: number; status?: string; sort?: string;
    limit?: number; offset?: number;
  } = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.append(k, String(v));
    });
    const s = qs.toString();
    return api.get<{ results: HistoryRow[]; limit: number; offset: number; total: number }>(
      `/results${s ? `?${s}` : ''}`);
  },
  getResult: (id: number) => api.get<ResultDetail>(`/results/${id}`),
  editCandidate: (id: number, body: Partial<Candidate>) =>
    api.put<{ candidate: Candidate }>(`/results/${id}/candidate`, body),
  overrideAnswers: (
    id: number,
    answers: Array<{ question_no: number; marked_option: string | null }>,
  ) => api.post<{ evaluation: ResultDetail['evaluation'] }>(`/results/${id}/answers`, answers),
  deleteResult: (id: number) => api.del<{ deleted: boolean }>(`/results/${id}`),

  createReport: (submissionId: number) =>
    api.post<{ report: ReportMeta }>(`/results/${submissionId}/report`),
  listReports: () => api.get<{ reports: ReportMeta[] }>('/reports'),

  testResults: (testId: number) =>
    api.get<TestResultsResponse>(`/tests/${testId}/results`),
  audit: () => api.get<{ events: Array<{ id: number; action: string; entity: string | null; entity_id: number | null; detail: Record<string, unknown>; created_at: string }> }>('/audit'),
};

/** Source for the scanned sheet image.
 *
 *  The route is authenticated, so the bearer token travels as a header on the
 *  image request itself -- React Native's <Image> supports this, and it keeps
 *  the token out of the URL (and therefore out of logs and caches).
 */
export function sheetImageSource(
  submissionId: number,
  variant: 'original' | 'annotated' = 'original',
): { uri: string; headers: Record<string, string> } {
  const token = getToken();
  const path = variant === 'annotated' ? 'annotated' : 'sheet';
  return {
    uri: `${getBaseUrl()}/results/${submissionId}/${path}`,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  };
}

/** Report download URL plus the auth header it needs. */
export function reportDownload(reportId: number): {
  url: string; headers: Record<string, string>;
} {
  const token = getToken();
  return {
    url: `${getBaseUrl()}/reports/${reportId}/download`,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  };
}

export { request };
