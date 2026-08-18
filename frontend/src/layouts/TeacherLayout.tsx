import { RoleLayout } from "./RoleLayout";
import { roleRouteDefinitions } from "../routes/config";

export function TeacherLayout() {
  return <RoleLayout definition={roleRouteDefinitions.teacher} />;
}
