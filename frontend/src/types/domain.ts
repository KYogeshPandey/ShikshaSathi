export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

interface ActiveResource {
  id: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface UserDirectoryEntry {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "teacher" | "student";
  is_active: boolean;
  created_at: string;
}

export interface Classroom extends ActiveResource {
  name: string;
  code: string;
  grade_level: string | null;
  section: string | null;
}

export interface ClassroomCreate {
  name: string;
  code: string;
  grade_level?: string | null;
  section?: string | null;
}

export interface ClassroomUpdate {
  name?: string;
  grade_level?: string | null;
  section?: string | null;
  is_active?: boolean;
}

export interface Subject extends ActiveResource {
  name: string;
  code: string;
  is_elective: boolean;
}

export interface SubjectCreate {
  name: string;
  code: string;
  is_elective?: boolean;
}

export interface SubjectUpdate {
  name?: string;
  is_elective?: boolean;
  is_active?: boolean;
}

export interface TeacherProfile extends ActiveResource {
  user_id: string;
  employee_code: string | null;
  phone_number: string | null;
}

export interface TeacherProfileCreate {
  user_id: string;
  employee_code?: string | null;
  phone_number?: string | null;
}

export interface TeacherProfileUpdate {
  employee_code?: string | null;
  phone_number?: string | null;
  is_active?: boolean;
}

export interface StudentProfile extends ActiveResource {
  user_id: string;
  full_name?: string | null;
  classroom_id: string | null;
  roll_number: string | null;
}

export interface StudentProfileCreate {
  user_id: string;
  classroom_id?: string | null;
  roll_number?: string | null;
}

export interface StudentProfileUpdate {
  classroom_id?: string | null;
  roll_number?: string | null;
  is_active?: boolean;
}

export interface StudentMembershipUpdate {
  classroom_id: string | null;
  roll_number?: string | null;
}

export interface TeacherAssignment extends ActiveResource {
  teacher_profile_id: string;
  classroom_id: string;
  subject_id: string;
}

export interface TeacherAssignmentCreate {
  teacher_profile_id: string;
  classroom_id: string;
  subject_id: string;
}

export type DayOfWeek =
  | "monday"
  | "tuesday"
  | "wednesday"
  | "thursday"
  | "friday"
  | "saturday"
  | "sunday";

export interface TimetableEntry extends ActiveResource {
  classroom_id: string;
  subject_id: string;
  teacher_profile_id: string;
  day_of_week: DayOfWeek;
  start_time: string;
  end_time: string;
}

export interface TimetableEntryCreate {
  classroom_id: string;
  subject_id: string;
  teacher_profile_id: string;
  day_of_week: DayOfWeek;
  start_time: string;
  end_time: string;
}

export type TimetableEntryUpdate = Partial<TimetableEntryCreate> & {
  is_active?: boolean;
};

export type AnnouncementAudience = "all" | "classroom" | "teacher" | "student";

export interface Announcement extends ActiveResource {
  title: string;
  content: string;
  author_user_id: string;
  audience: AnnouncementAudience;
  classroom_ids: string[];
}

export interface AnnouncementCreate {
  title: string;
  content: string;
  audience: AnnouncementAudience;
  classroom_ids: string[];
}

export interface AnnouncementUpdate {
  title?: string;
  content?: string;
  is_active?: boolean;
}

export type AttendanceStatus = "present" | "absent";

export interface AttendanceRosterStudent {
  student_profile_id: string;
  full_name: string;
  roll_number: string | null;
}

export interface AttendanceRecord {
  id: string;
  student_profile_id: string;
  classroom_id: string;
  subject_id: string;
  attendance_date: string;
  status: AttendanceStatus;
  remarks: string | null;
  marked_by_user_id: string;
  created_at: string;
  updated_at: string;
}

export interface BulkAttendanceRequest {
  classroom_id: string;
  subject_id: string;
  attendance_date: string;
  records: Array<{
    student_profile_id: string;
    status: AttendanceStatus;
    remarks?: string | null;
  }>;
}

export interface AttendanceBulkSaveResult {
  classroom_id: string;
  subject_id: string;
  attendance_date: string;
  created_count: number;
  updated_count: number;
  total_count: number;
  record_ids: string[];
}

export interface DailyAttendanceResponse {
  classroom_id: string;
  subject_id: string;
  attendance_date: string;
  records: AttendanceRecord[];
}

export interface StudentSelfStats {
  student_profile_id: string;
  total_count: number;
  present_count: number;
  absent_count: number;
  attendance_percentage: number;
}

export type AttendancePlanStatus =
  | "safe"
  | "recovery_possible"
  | "tight_recovery"
  | "not_reachable";

export type SubjectAttendanceStatus =
  | "safe"
  | "near_target"
  | "recovery_needed"
  | "no_history";

export interface AttendancePlanCounts {
  attended: number;
  held: number;
  absent: number;
  percentage: number;
}

export interface SubjectAttendanceSummary extends AttendancePlanCounts {
  subject_id: string;
  subject_name: string;
  subject_code: string;
  status: SubjectAttendanceStatus;
}

export interface AttendanceRecoveryPlanRequest {
  target_percentage: number;
  deadline: string;
  subject_id?: string;
}

export interface AttendanceRecoveryPlan {
  scope: "overall" | "subject";
  subject_id: string | null;
  subject_name: string | null;
  target_percentage: number;
  deadline: string;
  current: AttendancePlanCounts;
  overall: AttendancePlanCounts;
  overall_status: SubjectAttendanceStatus;
  subjects: SubjectAttendanceSummary[];
  status: AttendancePlanStatus;
  reachable: boolean;
  classes_required: number | null;
  scheduled_classes_remaining: number;
  scheduled_teaching_days_remaining: number;
  teaching_days_required: number | null;
  recovery_date: string | null;
  projected_attendance_percentage: number;
  projected_max_percentage: number;
  attendance_buffer_classes: number;
  schedule_assumption: string;
}

export type AnalyticsWindowDays = 7 | 30;

export interface AnalyticsPeriod {
  days: AnalyticsWindowDays;
  date_from: string;
  date_to: string;
}

export interface AnalyticsAttendanceMetric {
  total_count: number;
  present_count: number;
  absent_count: number;
  attendance_percentage: number;
}

export interface AnalyticsTrendPoint extends AnalyticsAttendanceMetric {
  attendance_date: string;
}

export interface AnalyticsOverview {
  role: "admin" | "teacher" | "student";
  period: AnalyticsPeriod;
  attendance: AnalyticsAttendanceMetric;
  comparison: {
    period: AnalyticsPeriod;
    attendance: AnalyticsAttendanceMetric;
    percentage_point_change: number | null;
  };
  trend: AnalyticsTrendPoint[];
  attendance_definition: "present_marked_records_divided_by_all_marked_records";
  missing_records_policy: "excluded_unmarked";
  admin_population: {
    active_students: number;
    active_teachers: number;
    active_classrooms: number;
    active_subjects: number;
  } | null;
  teacher_scope: {
    assigned_classrooms: number;
    assigned_subjects: number;
    timetable_slots: number;
  } | null;
  student_context: {
    roll_number: string | null;
  } | null;
  attention_classrooms: Array<
    AnalyticsAttendanceMetric & {
      classroom_name: string;
      classroom_code: string;
    }
  >;
}

export interface ReportPeriod {
  month: string | null;
  date_from: string;
  date_to: string;
}

export interface AttendanceReportSummary {
  total_count: number;
  present_count: number;
  absent_count: number;
  attendance_percentage: number;
}

export interface AttendanceReportDetailRow {
  attendance_date: string;
  student_profile_id: string;
  roll_number: string | null;
  full_name: string;
  status: AttendanceStatus;
  remarks: string | null;
}

export interface AttendanceReport {
  classroom_id: string;
  subject_id: string;
  student_profile_id: string | null;
  period: ReportPeriod;
  summary: AttendanceReportSummary;
  details: AttendanceReportDetailRow[];
}

export interface StudentAttendanceReportRow {
  student_profile_id: string;
  roll_number: string | null;
  full_name: string;
  total_count: number;
  present_count: number;
  absent_count: number;
  attendance_percentage: number;
}

export interface DefaultersReport {
  classroom_id: string;
  subject_id: string;
  period: ReportPeriod;
  threshold: number;
  zero_attendance_policy: "included_as_zero_percent";
  students: StudentAttendanceReportRow[];
}

export interface LeaderboardRow extends StudentAttendanceReportRow {
  rank: number;
}

export interface LeaderboardReport {
  classroom_id: string;
  subject_id: string;
  period: ReportPeriod;
  tie_breaking: "percentage_desc_roll_number_asc_student_profile_id_asc";
  students: LeaderboardRow[];
}

export type RecognitionDecision = "found" | "unknown" | "ambiguous";

export interface RecognitionAttendanceAttempt {
  attempt_id: string;
  classroom_id: string;
  subject_id: string;
  attendance_date: string;
  decision: RecognitionDecision;
  matched_student_profile_id: string | null;
  attendance_record_id: string | null;
  requires_confirmation: boolean;
}

export interface RecognitionAttendanceConfirmation {
  attempt_id: string;
  decision: RecognitionDecision;
  confirmed_student_profile_id: string;
  attendance_record_id: string;
}

export interface RecognitionAttendanceProposal {
  attempt_id: string;
  face_index: number;
  decision: RecognitionDecision;
  matched_student_profile_id: string | null;
  best_similarity: number | null;
  is_duplicate: boolean;
}

export interface RecognitionAttendanceReview {
  review_id: string;
  classroom_id: string;
  subject_id: string;
  attendance_date: string;
  face_count: number;
  proposals: RecognitionAttendanceProposal[];
}

export interface RecognitionAttendanceReviewConfirmation {
  review_id: string;
  attendance_record_ids: string[];
  confirmed_records: Array<{
    student_profile_id: string;
    status: AttendanceStatus;
  }>;
}

export type BulkImportEntity =
  | "classrooms"
  | "subjects"
  | "teacher-profiles"
  | "student-profiles";

export interface BulkImportResult {
  entity: BulkImportEntity;
  success: boolean;
  total_rows: number;
  imported_count: number;
  failed_count: number;
  errors: Array<{ row_number: number; code: string; message: string }>;
}

export interface StudentOnboardingIssue {
  code: string;
  message: string;
}

export interface StudentOnboardingStudentResult {
  row_number: number;
  student_profile_id: string | null;
  full_name: string | null;
  roll_number: string | null;
  profile_status: "created" | "updated" | "reactivated" | "existing" | "failed";
  photo_filename: string | null;
  photo_status: "not_provided" | "matched" | "missing" | "duplicate" | "invalid";
  biometric_status:
    | "not_requested"
    | "not_processed"
    | "enrolled"
    | "failed"
    | "already_enrolled";
  issues: StudentOnboardingIssue[];
}

export interface StudentOnboardingResult {
  classroom_id: string;
  classroom_name: string;
  total_students: number;
  profile_success_count: number;
  face_success_count: number;
  students: StudentOnboardingStudentResult[];
  unmatched_files: Array<{ filename: string; code: string; message: string }>;
}
