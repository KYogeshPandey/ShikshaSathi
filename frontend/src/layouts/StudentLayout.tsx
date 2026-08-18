import { RoleLayout } from "./RoleLayout";
import { roleRouteDefinitions } from "../routes/config";

export function StudentLayout() {
  return <RoleLayout definition={roleRouteDefinitions.student} />;
}
