// API response types matching server/views.py output

export interface AuthResponse {
  user_id: number;
  username: string;
  token: string;
}

export interface Module {
  id: number;
  module_type: string;
  volume: number;
  active: boolean;
  cycle_time: number | null;
  ticks_until_cycle: number | null;
  capacitor_per_cycle: number | null;
  detection_range: number | null;
  scan_range: number | null;
}

export interface ActiveOrder {
  id: number;
  order_type: string;
  status: string;
  target_ship_id: number | null;
  target_object_id: number | null;
  target_x: number | null;
  target_y: number | null;
  target_z: number | null;
  desired_distance: number | null;
  orbit_radius: number | null;
}

export interface TargetLock {
  id: number;
  target_ship_id: number;
  status: string;
  ticks_remaining: number | null;
}

export interface WeaponAssignment {
  module_id: number;
  target_ship_id: number;
}

export interface BuildOrder {
  id: number;
  blueprint: string;
  status: string;
  ore_cost: number;
  ticks_remaining: number;
  total_ticks: number;
  factory_module_id: number;
}

export interface Ship {
  id: number;
  user_id: number | null;
  name: string;
  ship_class: string;
  pos_x: number;
  pos_y: number;
  pos_z: number;
  vel_x: number;
  vel_y: number;
  vel_z: number;
  ore: number;
  capacitor: number;
  max_capacitor: number;
  total_volume: number;
  used_volume: number;
  cargo_capacity: number;
  max_speed: number;
  acceleration: number;
  shield_hp: number;
  max_shield_hp: number;
  armor_hp: number;
  max_armor_hp: number;
  is_destroyed: boolean;
  signature_radius: number;
  docked_in_id: number | null;
  claimed_by_user_id: number | null;
  team_id: number | null;
  match_id: number | null;
  faction: string | null;
  modules: Module[];
  active_orders: ActiveOrder[];
  locks: TargetLock[];
  build_orders: BuildOrder[];
  weapon_assignments: WeaponAssignment[];
}

export interface NearbyContact {
  type: "ship" | "object";
  id: number;
  detail: number;
  pos_x: number;
  pos_y: number;
  pos_z: number;
  // Classification+ (detail >= 2)
  ship_class?: string;
  vel_x?: number;
  vel_y?: number;
  vel_z?: number;
  object_type?: string;
  ore_remaining?: number;
  // Identification+ (detail >= 3)
  name?: string;
  // Locked targets get HP
  shield_hp?: number;
  max_shield_hp?: number;
  armor_hp?: number;
  max_armor_hp?: number;
}

export interface GameEvent {
  id: number;
  tick: number;
  type: string;
  message: string;
  ship_id: number | null;
}

export interface PendingCommand {
  id: number;
  type: string;
  ship_id: number | null;
  status: string;
  rejection_reason: string | null;
  processed_at_tick: number | null;
}

export interface TeamInfo {
  id: number;
  name: string;
  faction: string;
}

export interface MatchInfo {
  id: number;
  name: string;
  status: string;
  team1_id: number;
  team2_id: number;
  started_at_tick: number | null;
  winner_team_id: number | null;
}

export interface BoardableShip {
  ship_id: number;
  ship_class: string;
  name: string;
}

export interface AvailableHull {
  ship_id: number;
  ship_class: string;
  docked_at_ship_id: number;
  hull_point_cost: number;
}

export interface ViewResponse {
  tick: number;
  points: number;
  ships: Ship[];
  available_hulls: AvailableHull[];
  free_hull_classes: string[];
  boardable_ships: BoardableShip[];
  nearby: NearbyContact[];
  events: GameEvent[];
  pending_commands: PendingCommand[];
  team: TeamInfo | null;
  match: MatchInfo | null;
}

export interface CommandResponse {
  command_id: number;
  type: string;
  ship_id: number | null;
  status: string;
  message: string;
}

export interface MatchListItem {
  id: number;
  name: string;
  status: string;
  team1_id: number;
  team2_id: number | null;
  team1_member_count?: number;
  team2_member_count?: number;
  team1_faction?: string;
  team2_faction?: string;
  winner_team_id: number | null;
  started_at_tick: number | null;
  ended_at_tick: number | null;
  created_at: string;
}

export interface TeamListItem {
  id: number;
  name: string;
  faction: string;
  member_count: number;
  created_at: string;
}

export interface MatchDetailTeam {
  id: number;
  name: string;
  faction: string;
  member_count: number;
  members?: string[];
}

export interface MatchDetailMothership {
  id: number;
  name: string;
  shield_hp: number;
  max_shield_hp: number;
  armor_hp: number;
  max_armor_hp: number;
  is_destroyed: boolean;
}

export interface MatchDetail {
  id: number;
  name: string;
  status: string;
  team1: MatchDetailTeam | null;
  team2: MatchDetailTeam | null;
  team1_mothership: MatchDetailMothership | null;
  team2_mothership: MatchDetailMothership | null;
  winner_team_id: number | null;
  started_at_tick: number | null;
  ended_at_tick: number | null;
  created_at: string;
}
