# ArchLens Documentation

Welcome to the ArchLens documentation! This folder contains comprehensive technical documentation covering all aspects of the ArchLens platform.

## 📚 Documentation Index

### 1. [High Level Design (HLD)](./HLD.md)
**File Size:** 16 KB | **Last Updated:** May 19, 2026

The HLD provides a strategic overview of the ArchLens architecture, covering:
- Executive summary and key capabilities
- System architecture and component overview
- Technology stack (Frontend, Backend, Infrastructure)
- Data flow architecture
- Security architecture
- Scalability & performance optimizations
- Deployment architecture
- Integration points with external services
- Disaster recovery & reliability
- Future enhancements and roadmap

**Target Audience:** Architects, Technical Leads, Product Managers, Stakeholders

---

### 2. [Low Level Design (LLD)](./LLD.md)
**File Size:** 19 KB | **Last Updated:** May 19, 2026

The LLD provides detailed implementation specifications, including:
- Detailed module architecture (Frontend & Backend)
- Pydantic data models and schemas
- Service layer design with function signatures
- API endpoint specifications
- Frontend component design (React/JSX)
- Configuration management
- Caching strategy (Plugin cache, Module archive)
- Error handling patterns
- Database schema (ChromaDB)
- Testing strategy (Unit & Integration tests)

**Target Audience:** Software Engineers, Developers, QA Engineers

---

### 3. [End-to-End Workflow](./WORKFLOW_END_TO_END.md)
**File Size:** 38 KB | **Last Updated:** May 19, 2026

The workflow document provides complete user journey and technical flow details:
- Complete user journey (5 phases)
- Step-by-step workflow with code examples
- Technical flow diagrams and sequence diagrams
- State transitions and state machines
- Error recovery flows (AI auto-fix, manual fix mode)
- Performance timeline and optimization opportunities

**Target Audience:** DevOps Engineers, Support Engineers, New Team Members, Product Managers

---

## 🎯 Quick Navigation

### For New Team Members
Start with this order:
1. Read [HLD Executive Summary](./HLD.md#1-executive-summary) (5 min)
2. Review [Workflow Overview](./WORKFLOW_END_TO_END.md#1-user-journey-overview) (10 min)
3. Study [System Architecture](./HLD.md#2-system-architecture) (15 min)
4. Explore [LLD Module Structure](./LLD.md#1-module-architecture) (20 min)

### For Troubleshooting
1. Check [Error Recovery Flows](./WORKFLOW_END_TO_END.md#5-error-recovery-flows)
2. Review [Error Handling](./LLD.md#8-error-handling)
3. Examine [State Transitions](./WORKFLOW_END_TO_END.md#4-state-transitions)

### For Performance Optimization
1. Review [Performance Timeline](./WORKFLOW_END_TO_END.md#6-performance-timeline)
2. Study [Caching Strategy](./LLD.md#7-caching-strategy)
3. Check [Scalability Considerations](./HLD.md#7-scalability--performance)

### For Architecture Review
1. Study [Component Overview](./HLD.md#3-component-overview)
2. Review [Data Flow Architecture](./HLD.md#5-data-flow-architecture)
3. Examine [Service Layer Design](./LLD.md#3-service-layer-design)

---

## 📊 Documentation Statistics

| Document | Lines | Sections | Diagrams | Code Examples |
|----------|-------|----------|----------|---------------|
| HLD.md | ~550 | 12 | 1 | 5 |
| LLD.md | ~850 | 10 | 0 | 15+ |
| WORKFLOW_END_TO_END.md | ~1400 | 6 | 4 | 20+ |
| **Total** | **~2800** | **28** | **5** | **40+** |

---

## 🛠️ Technology Stack Summary

### Frontend
- **Framework:** React 18.2.0
- **Build Tool:** Vite 5.4.21
- **Styling:** Tailwind CSS 3.x
- **HTTP Client:** Axios
- **Syntax Highlighting:** Prism
- **Notifications:** react-hot-toast
- **File Handling:** JSZip 3.x

### Backend
- **Framework:** FastAPI 0.100+
- **Server:** Uvicorn (ASGI)
- **Language:** Python 3.10
- **Data Validation:** Pydantic
- **Async:** AsyncIO
- **HTTP Client:** requests
- **AI SDK:** openai (Cloud AI Platform)
- **Vector DB:** ChromaDB

### Infrastructure
- **IaC Tool:** Terraform v1.15.3
- **Cache:** Plugin Cache (~/.archlens/)
- **Module Archive:** Module source cache

### AI Models
- **Analysis/WAF/Pricing:** Analysis LLM (Cloud AI Platform)
- **Terraform Generation/Fixes:** Code Generation LLM (Cloud AI Platform)

---

## 🔗 Related Resources

### Internal Links
- [Main README](../README.md) - Project overview and setup instructions
- [Backend README](../backend/README.md) - Backend-specific documentation
- [Frontend README](../frontend/README.md) - Frontend-specific documentation

### External References
- [Terraform Documentation](https://www.terraform.io/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)
- [Cloud AI Platform Service](https://azure.microsoft.com/en-us/products/ai-services/openai-service)
- [Cloud AI Platform](https://azure.microsoft.com/en-us/products/ai-foundry)

---

## 📝 Documentation Standards

### Keeping Documentation Updated
- Update version numbers when making significant changes
- Add "Last Updated" date at the bottom of each document
- Use consistent formatting and terminology
- Include code examples where applicable
- Keep diagrams synchronized with implementation

### Contributing to Documentation
1. Follow the existing structure and formatting
2. Use markdown features consistently
3. Add cross-references between documents
4. Include practical examples
5. Verify all technical details before committing

---

## 🏗️ Architecture Diagrams

All architecture diagrams in these documents use ASCII art for universal compatibility. For more detailed visual diagrams, consider using:
- Draw.io
- Lucidchart
- Mermaid (in markdown)
- PlantUML

---

## 📞 Support & Feedback

For questions, clarifications, or suggestions about this documentation:
- Open an issue in the project repository
- Contact the development team
- Propose changes via pull request

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | May 19, 2026 | Initial documentation creation | ArchLens Team |

---

**Last Updated:** May 19, 2026  
**Maintained By:** ArchLens Development Team
