import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Tenant, User, Project, ProjectDataSource, SyncHistory, SyncMetadata, TeamsMessage } from './entities';

@Module({
  imports: [
    TypeOrmModule.forRoot({
      type: 'postgres',
      url: process.env.DATABASE_URL,
      entities: [Tenant, User, Project, ProjectDataSource, SyncHistory, SyncMetadata, TeamsMessage],
      synchronize: false,
      logging: false,
    }),
    TypeOrmModule.forFeature([Tenant, User, Project, ProjectDataSource, SyncHistory, SyncMetadata, TeamsMessage]),
  ],
  exports: [TypeOrmModule],
})
export class DatabaseModule {}
