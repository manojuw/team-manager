import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { randomUUID } from 'crypto';
import { Project } from '../database/entities/project.entity';
import { CreateProjectDto } from './dto/create-project.dto';
import { UpdateProjectDto } from './dto/update-project.dto';

@Injectable()
export class ProjectsService {
  constructor(
    @InjectRepository(Project)
    private readonly projectRepository: Repository<Project>,
  ) {}

  async findAllByTenant(tenantId: string): Promise<Project[]> {
    return this.projectRepository.find({
      where: { tenant_id: tenantId },
      order: { created_at: 'DESC' },
    });
  }

  async findOneByTenant(id: string, tenantId: string): Promise<Project> {
    const project = await this.projectRepository.findOne({
      where: { id, tenant_id: tenantId },
    });
    if (!project) {
      throw new NotFoundException('Project not found');
    }
    return project;
  }

  async create(dto: CreateProjectDto, tenantId: string): Promise<Project> {
    const project = this.projectRepository.create({
      id: randomUUID(),
      name: dto.name,
      description: dto.description || undefined,
      tenant_id: tenantId,
    });
    return this.projectRepository.save(project);
  }

  async update(id: string, dto: UpdateProjectDto, tenantId: string): Promise<Project> {
    const project = await this.findOneByTenant(id, tenantId);
    if (dto.name !== undefined) project.name = dto.name;
    if (dto.description !== undefined) project.description = dto.description;
    return this.projectRepository.save(project);
  }

  async remove(id: string, tenantId: string): Promise<void> {
    const project = await this.findOneByTenant(id, tenantId);
    await this.projectRepository.remove(project);
  }
}
