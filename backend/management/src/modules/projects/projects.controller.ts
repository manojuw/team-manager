import { Controller, Get, Post, Put, Delete, Body, Param, UseGuards } from '@nestjs/common';
import { ProjectsService } from './projects.service';
import { CreateProjectDto } from './dto/create-project.dto';
import { UpdateProjectDto } from './dto/update-project.dto';
import { JwtAuthGuard } from '@/common/guards/jwt-auth.guard';
import { CurrentUser } from '@/common/decorators/current-user.decorator';
import { IAuthUser } from '@/common/interfaces/auth-user.interface';

@Controller('projects')
@UseGuards(JwtAuthGuard)
export class ProjectsController {
  constructor(private readonly projectsService: ProjectsService) {}

  @Get()
  async findAll(@CurrentUser() user: IAuthUser) {
    return this.projectsService.findAllByTenant(user.tenantId);
  }

  @Post()
  async create(@Body() dto: CreateProjectDto, @CurrentUser() user: IAuthUser) {
    return this.projectsService.create(dto, user.tenantId);
  }

  @Get(':id')
  async findOne(@Param('id') id: string, @CurrentUser() user: IAuthUser) {
    return this.projectsService.findOneByTenant(id, user.tenantId);
  }

  @Put(':id')
  async update(
    @Param('id') id: string,
    @Body() dto: UpdateProjectDto,
    @CurrentUser() user: IAuthUser,
  ) {
    return this.projectsService.update(id, dto, user.tenantId);
  }

  @Delete(':id')
  async remove(@Param('id') id: string, @CurrentUser() user: IAuthUser) {
    await this.projectsService.remove(id, user.tenantId);
    return { success: true };
  }
}
