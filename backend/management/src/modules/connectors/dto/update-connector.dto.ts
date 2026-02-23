import { IsOptional, IsObject, IsString } from 'class-validator';

export class UpdateConnectorDto {
  @IsOptional()
  @IsString()
  name?: string;

  @IsOptional()
  @IsObject()
  config?: Record<string, any>;
}
