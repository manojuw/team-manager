import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { randomUUID } from 'crypto';
import { ProjectDataSource } from '../database/entities/project-data-source.entity';
import { CreateDataSourceDto } from './dto/create-datasource.dto';
import { UpdateDataSourceDto } from './dto/update-datasource.dto';

@Injectable()
export class DataSourcesService {
  constructor(
    @InjectRepository(ProjectDataSource)
    private readonly dataSourceRepository: Repository<ProjectDataSource>,
  ) {}

  async findByProject(projectId: string, tenantId: string): Promise<ProjectDataSource[]> {
    const sources = await this.dataSourceRepository.find({
      where: { project_id: projectId, tenant_id: tenantId },
      order: { created_at: 'DESC' },
    });
    return sources.map((s) => this.sanitizeConfig(s));
  }

  async findOneByTenant(id: string, tenantId: string): Promise<ProjectDataSource> {
    const source = await this.dataSourceRepository.findOne({
      where: { id, tenant_id: tenantId },
    });
    if (!source) {
      throw new NotFoundException('Data source not found');
    }
    return source;
  }

  async getConfig(id: string, tenantId: string): Promise<Record<string, any>> {
    const source = await this.findOneByTenant(id, tenantId);
    const config = source.config || {};
    return {
      client_id: config.client_id || '',
      tenant_id: config.tenant_id || '',
      has_secret: !!(config.client_secret),
    };
  }

  async create(dto: CreateDataSourceDto, tenantId: string): Promise<ProjectDataSource> {
    const source = this.dataSourceRepository.create({
      id: randomUUID(),
      project_id: dto.projectId,
      source_type: dto.sourceType,
      config: dto.config || {},
      tenant_id: tenantId,
      sync_interval_minutes: dto.syncIntervalMinutes ?? 60,
      sync_enabled: dto.syncEnabled ?? false,
    });
    const saved = await this.dataSourceRepository.save(source);
    return this.sanitizeConfig(saved);
  }

  async update(id: string, dto: UpdateDataSourceDto, tenantId: string): Promise<ProjectDataSource> {
    const source = await this.findOneByTenant(id, tenantId);
    if (dto.sourceType !== undefined) source.source_type = dto.sourceType;
    if (dto.config !== undefined) source.config = dto.config;
    if (dto.syncIntervalMinutes !== undefined) source.sync_interval_minutes = dto.syncIntervalMinutes;
    if (dto.syncEnabled !== undefined) source.sync_enabled = dto.syncEnabled;
    const saved = await this.dataSourceRepository.save(source);
    return this.sanitizeConfig(saved);
  }

  async remove(id: string, tenantId: string): Promise<void> {
    const source = await this.findOneByTenant(id, tenantId);
    await this.dataSourceRepository.remove(source);
  }

  private sanitizeConfig(source: ProjectDataSource): ProjectDataSource {
    if (source.config) {
      const sanitized = { ...source.config };
      if (sanitized.client_secret) {
        sanitized.client_secret = '••••••••';
      }
      source.config = sanitized;
    }
    return source;
  }
}
