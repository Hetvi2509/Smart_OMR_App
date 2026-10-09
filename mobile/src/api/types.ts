/** Shapes returned by the API. Numerics arrive as strings from Postgres
 *  NUMERIC columns, so anything money/marks-like is typed `number | string`
 *  and must go through `num()` before arithmetic or toFixed. */

export type User = {
  id: number;
  email: string;
  full_name: string;
  role: string;
  institution_id: number | null;
  institution_name: string | null;
};

export type AuthResponse = { token: string; user: User };

export type Test = {
  id: number;
  name: string;
  subject: string | null;
  exam_date: string | null;
  layout: string;
  total_questions: number;
  options: string;
  marks_correct: number | string;
  marks_wrong: number | string;
  marks_blank: number | string;
  ambiguous_policy: string;
  floor_at_zero: boolean;
  status: string;
  created_at: string;
  updated_at: string;
  key_count?: number;
  submission_count?: number;
};

export type AnswerKeyEntry = {
  question_no: number;
  correct_option: string;
  marks?: number | string | null;
};

export type LayoutInfo = {
  key: string;
  name: string;
  blocks: number;
  rows_per_block: number;
  total_questions: number;
  options: string[];
  subjects: string[];
};

export type Candidate = {
  roll_no: string | null;
  student_name: string | null;
  class_std: string | null;
  section: string | null;
  registration_no: string | null;
  confidence?: number | string | null;
  engine?: string | null;
  edited_at?: string | null;
};

export type Score = {
  correct: number;
  wrong: number;
  unattempted: number;
  invalid: number;
  unscored: number;
  attempted: number;
  total: number;
  max: number;
  percentage: number;
  grade: string;
  subject_scores: Record<string, number>;
};

export type ScanResponse = {
  submission_id: number;
  evaluation_id: number;
  status: string;
  layout: string;
  answered: number;
  processing_ms: number;
  review_questions: number[];
  key_questions: number;
  candidate: Candidate;
  ocr: { confidence: number | null; engine: string | null; note: string | null };
  score: Score;
  test: { id: number; name: string; subject: string | null };
};

export type Evaluation = {
  id: number;
  correct_count: number;
  wrong_count: number;
  unattempted_count: number;
  invalid_count: number;
  unscored_count: number;
  total_marks: number | string;
  max_marks: number | string;
  percentage: number | string;
  grade: string | null;
  subject_scores: Record<string, number | string>;
  evaluated_at: string;
};

export type EvaluationItem = {
  question_no: number;
  subject: string | null;
  marked_option: string | null;
  expected_option: string | null;
  status: 'correct' | 'wrong' | 'unattempted' | 'invalid' | 'unscored';
  marks: number | string;
  needs_review: boolean;
  note: string | null;
};

export type DetectedAnswer = {
  question_no: number;
  subject: string | null;
  marked_option: string | null;
  verdict: string;
  confidence: number | string | null;
  needs_review: boolean;
};

export type Submission = {
  id: number;
  test_id: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  image_path: string | null;
  error_reason: string | null;
  error_hint: string | null;
  layout_used: string | null;
  answered_count: number | null;
  review_questions: number[];
  processing_ms: number | null;
  created_at: string;
  processed_at: string | null;
};

export type ResultDetail = {
  submission: Submission;
  test: Test & { institution_name?: string | null };
  candidate: Candidate;
  evaluation: Evaluation | null;
  items: EvaluationItem[];
  detected: DetectedAnswer[];
  reports: ReportMeta[];
};

export type HistoryRow = {
  submission_id: number;
  status: Submission['status'];
  created_at: string;
  processed_at: string | null;
  error_reason: string | null;
  error_hint: string | null;
  answered_count: number | null;
  processing_ms: number | null;
  layout_used: string | null;
  review_questions: number[];
  test_id: number;
  test_name: string;
  subject: string | null;
  roll_no: string | null;
  student_name: string | null;
  class_std: string | null;
  section: string | null;
  registration_no: string | null;
  total_marks: number | string | null;
  max_marks: number | string | null;
  percentage: number | string | null;
  grade: string | null;
  correct_count: number | null;
  wrong_count: number | null;
  unattempted_count: number | null;
  invalid_count: number | null;
  evaluated_at: string | null;
};

export type ReportMeta = {
  id: number;
  kind: string;
  file_size: number | null;
  created_at: string;
  submission_id?: number;
  test_name?: string | null;
  student_name?: string | null;
  roll_no?: string | null;
};

export type DashboardData = {
  stats: {
    tests: number;
    scans: number;
    completed: number;
    failed: number;
    reports: number;
    avg_percentage: number | string | null;
    scans_7d: number;
  };
  recent: Array<{
    submission_id: number;
    status: Submission['status'];
    created_at: string;
    test_name: string;
    student_name: string | null;
    roll_no: string | null;
    percentage: number | string | null;
    grade: string | null;
    total_marks: number | string | null;
    max_marks: number | string | null;
  }>;
  by_test: Array<{
    id: number;
    name: string;
    evaluated: number;
    avg_percentage: number | string | null;
    best_percentage: number | string | null;
  }>;
  user: User;
};

export type TestResultsResponse = {
  results: Array<{
    submission_id: number;
    status: Submission['status'];
    created_at: string;
    roll_no: string | null;
    student_name: string | null;
    class_std: string | null;
    section: string | null;
    total_marks: number | string | null;
    max_marks: number | string | null;
    percentage: number | string | null;
    grade: string | null;
    correct_count: number | null;
    wrong_count: number | null;
    unattempted_count: number | null;
  }>;
  summary: {
    evaluated: number;
    avg_pct: number | string | null;
    max_pct: number | string | null;
    min_pct: number | string | null;
  };
};

export type Health = {
  status: string;
  database: string;
  ocr_enabled: boolean;
  ocr_available: boolean;
  version: string;
};

/** Postgres NUMERIC arrives as a string; coerce before any maths. */
export function num(value: number | string | null | undefined): number {
  if (value === null || value === undefined) return 0;
  const n = typeof value === 'number' ? value : parseFloat(value);
  return Number.isFinite(n) ? n : 0;
}
