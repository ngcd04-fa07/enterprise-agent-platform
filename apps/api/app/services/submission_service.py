import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.submission import Submission, SubmissionStatus
from app.repositories.submission_repository import SubmissionRepository


class SubmissionNotFoundError(Exception):
    """Raised both when a submission doesn't exist and when it exists in a
    different organisation than the caller's. Deliberately the same error
    either way — a cross-tenant ID guess must never be able to distinguish
    "wrong org" from "doesn't exist" via a different error shape.
    """


class SubmissionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._submissions = SubmissionRepository(session)

    async def create_submission(
        self, *, organisation_id: uuid.UUID, created_by_user_id: uuid.UUID, title: str
    ) -> Submission:
        return await self._submissions.create(
            organisation_id=organisation_id, created_by_user_id=created_by_user_id, title=title
        )

    async def get_submission(
        self, *, organisation_id: uuid.UUID, submission_id: uuid.UUID
    ) -> Submission:
        submission = await self._submissions.get(
            organisation_id=organisation_id, submission_id=submission_id
        )
        if submission is None:
            raise SubmissionNotFoundError(submission_id)
        return submission

    async def list_submissions(self, *, organisation_id: uuid.UUID) -> list[Submission]:
        return await self._submissions.list_for_organisation(organisation_id)

    async def update_submission(
        self,
        *,
        organisation_id: uuid.UUID,
        submission_id: uuid.UUID,
        title: str | None = None,
        status: SubmissionStatus | None = None,
    ) -> Submission:
        submission = await self.get_submission(
            organisation_id=organisation_id, submission_id=submission_id
        )
        if title is not None:
            submission.title = title
        if status is not None:
            submission.status = status
        await self._session.flush()
        return submission
