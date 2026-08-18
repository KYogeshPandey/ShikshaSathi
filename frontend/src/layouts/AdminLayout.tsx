import { RoleLayout } from "./RoleLayout";
import { roleRouteDefinitions } from "../routes/config";

export function AdminLayout() {
  return <RoleLayout definition={roleRouteDefinitions.admin} />;
}
