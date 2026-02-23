import { Entity, PrimaryColumn, Column, CreateDateColumn, ManyToOne, JoinColumn, OneToMany } from 'typeorm';
import { Tenant } from './tenant.entity';
import { Connector } from './connector.entity';

@Entity('project')
export class Project {
  @PrimaryColumn({ type: 'text' })
  id: string;

  @Column({ type: 'text' })
  name: string;

  @Column({ type: 'text', nullable: true })
  description: string;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  created_at: Date;

  @Column({ type: 'uuid', nullable: true, name: 'tenant_id' })
  tenant_id: string;

  @ManyToOne(() => Tenant, (tenant) => tenant.projects)
  @JoinColumn({ name: 'tenant_id' })
  tenant: Tenant;

  @OneToMany(() => Connector, (c) => c.project)
  connectors: Connector[];
}
