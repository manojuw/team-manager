import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { randomUUID } from 'crypto';
import { DataSource } from '../database/entities/data-source.entity';
import { Connector } from '../database/entities/connector.entity';
import { CreateDataSourceDto } from './dto/create-datasource.dto';
import { UpdateDataSourceDto } from './dto/update-datasource.dto';

@Injectable()
export class DataSourcesService {
  constructor(
    @InjectRepository(DataSource)
    private readonly dataSourceRepository: Repository<DataSource>,
    @InjectRepository(Connector)
    private readonly connectorRepository: Repository<Connector>,
  ) {}

  async findByConnector(connectorId: string, tenantId: string): Promise<DataSource[]> {
    return this.dataSourceRepository.find({
      where: { connector_id: connectorId, tenant_id: tenantId },
      order: { created_at: 'DESC' },
    });
  }

  async findByProject(projectId: string, tenantId: string): Promise<DataSource[]> {
    return this.dataSourceRepository.find({
      where: { project_id: projectId, tenant_id: tenantId },
      order: { created_at: 'DESC' },
    });
  }

  async findOneByTenant(id: string, tenantId: string): Promise<DataSource> {
    const source = await this.dataSourceRepository.findOne({
      where: { id, tenant_id: tenantId },
    });
    if (!source) {
      throw new NotFoundException('Data source not found');
    }
    return source;
  }

  async create(dto: CreateDataSourceDto, tenantId: string): Promise<DataSource> {
    const connector = await this.connectorRepository.findOne({
      where: { id: dto.connectorId, tenant_id: tenantId },
    });
    if (!connector) {
      throw new NotFoundException('Connector not found');
    }

    const source = this.dataSourceRepository.create({
      id: randomUUID(),
      connector_id: dto.connectorId,
      project_id: connector.project_id,
      tenant_id: tenantId,
      name: dto.name,
      source_type: dto.sourceType,
      config: dto.config || {},
      sync_interval_minutes: dto.syncIntervalMinutes ?? 60,
      sync_enabled: dto.syncEnabled ?? false,
    });
    return this.dataSourceRepository.save(source);
  }

  async update(id: string, dto: UpdateDataSourceDto, tenantId: string): Promise<DataSource> {
    const source = await this.findOneByTenant(id, tenantId);
    if (dto.name !== undefined) source.name = dto.name;
    if (dto.config !== undefined) source.config = dto.config;
    if (dto.syncIntervalMinutes !== undefined) source.sync_interval_minutes = dto.syncIntervalMinutes;
    if (dto.syncEnabled !== undefined) source.sync_enabled = dto.syncEnabled;
    return this.dataSourceRepository.save(source);
  }

  async remove(id: string, tenantId: string): Promise<void> {
    const source = await this.findOneByTenant(id, tenantId);
    await this.dataSourceRepository.remove(source);
  }
}
