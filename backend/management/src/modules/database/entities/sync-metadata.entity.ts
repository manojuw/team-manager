import { Entity, PrimaryColumn, Column } from 'typeorm';

@Entity('sync_metadata')
export class SyncMetadata {
  @PrimaryColumn({ type: 'text' })
  id: string;

  @Column({ type: 'text', name: 'team_id' })
  team_id: string;

  @Column({ type: 'text', name: 'channel_id' })
  channel_id: string;

  @Column({ type: 'text', name: 'last_sync' })
  last_sync: string;

  @Column({ type: 'timestamptz', nullable: true, name: 'updated_at' })
  updated_at: Date;

  @Column({ type: 'text', nullable: true, name: 'project_id' })
  project_id: string;

  @Column({ type: 'uuid', nullable: true, name: 'tenant_id' })
  tenant_id: string;
}
