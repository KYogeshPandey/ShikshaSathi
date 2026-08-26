export const queryKeys = {
  classrooms: ["academics", "classrooms"] as const,
  subjects: ["academics", "subjects"] as const,
  assignments: ["academics", "teacher-assignments"] as const,
  timetable: ["academics", "timetable"] as const,
  teachers: ["profiles", "teachers"] as const,
  teacherMe: ["profiles", "teacher", "me"] as const,
  students: ["profiles", "students"] as const,
  users: (role: "teacher" | "student") => ["users", role] as const,
  studentMe: ["profiles", "student", "me"] as const,
  announcements: ["announcements"] as const,
  attendance: ["attendance"] as const,
  attendanceRoster: (classroomId: string, subjectId: string) =>
    ["attendance", "roster", classroomId, subjectId] as const,
  studentAttendance: ["attendance", "me"] as const,
  attendanceRecoveryPlan: (filters: object) =>
    ["attendance", "me", "recovery-plan", filters] as const,
  analyticsOverview: (days: 7 | 30) => ["analytics", "overview", days] as const,
  reports: ["reports"] as const,
  attendanceReport: (filters: object) => ["reports", "attendance", filters] as const,
  defaultersReport: (filters: object) => ["reports", "defaulters", filters] as const,
  leaderboardReport: (filters: object) => ["reports", "leaderboard", filters] as const,
};
