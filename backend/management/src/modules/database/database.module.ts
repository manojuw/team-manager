import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Tenant, User, Project, DataSource, SyncHistory, SyncMetadata, SemanticData } from './entities';

@Module({
  imports: [
    TypeOrmModule.forRoot({
      type: 'postgres',
      url: process.env.DATABASE_URL,
      entities: [Tenant, User, Project, DataSource, SyncHistory, SyncMetadata, SemanticData],
      synchronize: false,
      logging: false,
    }),
    TypeOrmModule.forFeature([Tenant, User, Project, DataSource, SyncHistory, SyncMetadata, SemanticData]),
  ],
  exports: [TypeOrmModule],
})
export class DatabaseModule {}
